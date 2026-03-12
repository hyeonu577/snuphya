import datetime
import json
import logging

import requests

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


def load_cookies():
    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cookies = data.get('cookies')
        if cookies:
            return cookies
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def login_and_get_cookies():
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
    return True
