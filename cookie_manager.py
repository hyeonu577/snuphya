import datetime
import json
import logging
from contextlib import nullcontext

import requests

import healthcheck
import scraper
import snulogin
from config import BASE_URL, COOKIE_FILE, MAX_DRIVER_RETRIES

logger = logging.getLogger('snuphya')


class SessionExpiredError(Exception):
    pass


def save_cookies(cookies):
    data = {
        'cookies': cookies,
        'saved_at': str(datetime.datetime.now()),
    }
    with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    logger.info('cookies saved')


def _read_cookie_file():
    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_cookies():
    data = _read_cookie_file()
    if data is None:
        return None
    return data.get('cookies') or None


def is_first_login_of_day():
    data = _read_cookie_file()
    if data is None:
        return True
    try:
        saved_at = datetime.datetime.fromisoformat(data['saved_at'])
    except (KeyError, TypeError, ValueError):
        return True
    return saved_at.date() != datetime.date.today()


def login_and_get_cookies():
    # The day's first login needs a fresh 2FA round trip and can outrun the
    # healthcheck grace period, so keep the check up while it runs.
    if is_first_login_of_day():
        logger.info('first login of the day, sending healthcheck heartbeat while logging in')
        heartbeat = healthcheck.heartbeat('first login of the day in progress')
    else:
        heartbeat = nullcontext()

    with heartbeat:
        for i in range(1, MAX_DRIVER_RETRIES + 1):
            try:
                driver = scraper.get_driver()
                driver.get(url=f'{BASE_URL}/intranet/')
                snulogin.snu_login(driver)
                cookies = driver.get_cookies()
                cookies = {cookie['name']: cookie['value'] for cookie in cookies}
                driver.quit()
                save_cookies(cookies)
                return cookies
            except Exception:
                try:
                    driver.quit()
                except Exception:
                    pass
                if i == MAX_DRIVER_RETRIES:
                    raise
                continue

    raise RuntimeError('login retries exhausted')


def get_cookies():
    cookies = load_cookies()
    if cookies is None:
        return login_and_get_cookies()
    return cookies


def is_session_valid(response):
    if 'sso.snu.ac.kr' in response.url:
        return False
    if 'data-authtype="id"' in response.text:
        return False
    if '회원전용 페이지입니다' in response.text:
        return False
    return True
