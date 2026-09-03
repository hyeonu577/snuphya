import datetime

import cookie_manager
import db
import scraper
from config import ANNOUNCEMENT_URLS


def main():
    db.init_db()
    cookies = cookie_manager.get_cookies()

    cutoff = datetime.date.today() - datetime.timedelta(days=7)
    seen = set()
    results = []

    for url in ANNOUNCEMENT_URLS:
        soup, response = scraper.get_soup_from_url(url, cookies)
        if not cookie_manager.is_session_valid(response):
            cookies = cookie_manager.login_and_get_cookies()
            soup, response = scraper.get_soup_from_url(url, cookies)

        for row in scraper.get_online_announcement_list(soup):
            if row.find('span') is None or row.find('span').string is None:
                continue

            title = scraper.get_title(row)
            category = scraper.get_category(row)

            if (category, title) in seen:
                continue
            seen.add((category, title))

            date_str = row.find_all('td')[-1].get_text(strip=True)
            try:
                date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if date < cutoff:
                continue

            try:
                view_count = scraper.get_view_count(row)
            except ValueError:
                continue

            my_clicks = db.get_click_count(db.get_xxh3_128(category + title))
            actual = view_count - my_clicks
            results.append((category, title, date, view_count, my_clicks, actual))

    results.sort(key=lambda x: x[2], reverse=True)
    for category, title, date, view_count, my_clicks, actual in results:
        print(f'[{category}] {title}  ({date})')
        print(f'  겉보기: {view_count} / 내 클릭: {my_clicks} / 실질: {actual}')
        print()


if __name__ == '__main__':
    main()
