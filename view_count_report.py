import os
import datetime
import sqlite3
import time
import xxhash
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import snulogin

load_dotenv()

CURRENT_PATH = f'{Path(__file__).resolve().parent}/'
DB_PATH = f'{CURRENT_PATH}checked_items.db'


def get_driver():
    chrome_option = webdriver.ChromeOptions()
    chrome_option.add_argument("--headless")
    chrome_option.add_argument('--window-size=1920,1080')
    chrome_option.add_argument('--no-sandbox')
    chrome_option.add_argument('--disable-dev-shm-usage')
    chrome_option.add_argument('--disable-browser-side-navigation')

    prefs = {
        "download.default_directory": f'{CURRENT_PATH}file/',
        "download.prompt_for_download": False,
    }
    chrome_option.add_experimental_option("prefs", prefs)

    chrome_option.binary_location = os.getenv('CHROMIUM_PATH')
    chromedriver_path = os.getenv('CHROME_DRIVER_PATH')

    s = Service(chromedriver_path)
    driver_ = webdriver.Chrome(service=s, options=chrome_option)
    driver_.implicitly_wait(20)
    return driver_


def get_xxh3_128(string):
    byte_string = string.encode('utf-8')
    return xxhash.xxh3_128(byte_string).hexdigest()


def get_click_count(title_hash):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT click_count FROM click_counts WHERE title_hash = ?', (title_hash,))
        result = cursor.fetchone()
    return result[0] if result else 0


def get_list_urls():
    return [
        ('대학원', 'https://physics.snu.ac.kr/intranet/index.php?mid=board&pid=board&bbsid=graduate&sc=y'),
        ('대학원', 'https://physics.snu.ac.kr/intranet/index.php?mid=board&pid=board&bbsid=graduate&page=2'),
        ('학부', 'https://physics.snu.ac.kr/intranet/index.php?mid=board&pid=board&bbsid=undergraduate&sc=y'),
        ('학부', 'https://physics.snu.ac.kr/intranet/index.php?mid=board&pid=board&bbsid=undergraduate&page=2'),
    ]


def main():
    driver = get_driver()
    driver.get(url='https://physics.snu.ac.kr/intranet/')
    snulogin.snu_login(driver)
    time.sleep(3)

    cutoff = datetime.date.today() - datetime.timedelta(days=7)
    seen_titles = set()
    results = []

    for category, url in get_list_urls():
        driver.get(url=url)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        table = soup.find('tbody')
        if not table:
            continue
        rows = table.find_all('tr')

        for row in rows:
            title = row.find('span')
            if not title or not title.string:
                continue
            title = title.string

            if (category, title) in seen_titles:
                continue
            seen_titles.add((category, title))

            date_str = row.find_all('td')[-1].get_text(strip=True)
            try:
                date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            if date < cutoff:
                continue

            view_count = int(row.find_all('td')[-2].get_text(strip=True))
            title_hash = get_xxh3_128(category + title)
            my_clicks = get_click_count(title_hash)
            actual = view_count - my_clicks

            results.append((category, title, date, view_count, my_clicks, actual))

    driver.quit()

    results.sort(key=lambda x: x[2], reverse=True)

    for category, title, date, view_count, my_clicks, actual in results:
        print(f'[{category}] {title}  ({date})')
        print(f'  겉보기: {view_count} / 내 클릭: {my_clicks} / 실질: {actual}')
        print()


if __name__ == '__main__':
    main()
