import base64
import datetime
import json
import logging
import os
import random
import re
import traceback

import requests
from bs4 import BeautifulSoup
from html2text import html2text
from requests.cookies import cookiejar_from_dict
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from true_email import true_email

import cookie_manager

import db
from config import (
    ANNOUNCEMENT_FOLDER,
    BASE_URL,
    FILE_FOLDER,
    IMAGE_FOLDER,
    MAX_TEXT_FETCH_RETRIES,
)

logger = logging.getLogger('snuphya')


# --- Driver & page helpers ---

def get_driver():
    chrome_option = webdriver.ChromeOptions()
    chrome_option.add_argument("--headless")
    chrome_option.add_argument('--window-size=1920,1080')
    chrome_option.add_argument('--no-sandbox')
    chrome_option.add_argument('--disable-dev-shm-usage')
    chrome_option.add_argument('--disable-browser-side-navigation')

    prefs = {
        "download.default_directory": FILE_FOLDER,
        "download.prompt_for_download": False,
    }
    chrome_option.add_experimental_option("prefs", prefs)

    chrome_option.binary_location = os.getenv('CHROMIUM_PATH')
    chromedriver_path = os.getenv('CHROME_DRIVER_PATH')

    s = Service(chromedriver_path)
    driver = webdriver.Chrome(service=s, options=chrome_option)
    driver.implicitly_wait(20)
    return driver


def get_soup_from_url(url, cookies):
    response = requests.get(url, cookies=cookies)
    return BeautifulSoup(response.text, 'html.parser'), response


# --- Row parsing helpers ---

def get_online_announcement_list(soup):
    table = soup.find('tbody')
    return table.find_all('tr')


def get_title(row):
    return row.find('span').string


def get_view_count(row):
    return int(row.find_all('td')[-2].get_text(strip=True))


def get_link(row):
    return BASE_URL + row.a['href']


def get_category(row):
    link = get_link(row)
    if 'id=undergraduate' in link:
        return '학부'
    elif 'id=graduate' in link:
        return '대학원'
    return '?'


def need_to_be_checked(row):
    title_hash = db.get_xxh3_128(get_title(row))
    if not db.is_checked(title_hash):
        return True
    date_str = row.find_all('td')[-1].get_text(strip=True)
    date_datetime = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    if date_datetime.date() == datetime.datetime.today().date():
        return True
    if random.random() < 1 / 5:
        return True
    return False


# --- Content fetching ---

def get_text(cookies, link, title, category):
    for _ in range(MAX_TEXT_FETCH_RETRIES):
        response = requests.get(link, cookies=cookies)
        if not cookie_manager.is_session_valid(response):
            raise cookie_manager.SessionExpiredError()
        db.increment_click_count(db.get_xxh3_128(category + title), title)
        soup = BeautifulSoup(response.text, 'html.parser')
        content = soup.find(class_='board-content clearfix')
        if content is not None:
            return html2text(str(content)), response
    raise Exception('reached maximum iteration')


def get_image_url(body):
    pattern = r'\(([^()]*\.(?:png|jpg|PNG|JPG))\)'
    matches = re.findall(pattern, body)
    return [f'{BASE_URL}{url}' for url in matches]


def download_image(img_url, cookies):
    session = requests.Session()
    session.cookies = cookiejar_from_dict(cookies)

    image_type = img_url.split('.')[-1]
    image_path = f"{IMAGE_FOLDER}/image.{image_type}"
    response = session.get(img_url)
    if response.status_code == 200:
        with open(image_path, "wb") as f:
            f.write(response.content)
        logger.info(f"image downloaded: {image_path}")
        return _file_to_base64(image_path)
    else:
        logger.info("이미지 다운로드 실패")
        return False


# --- File download ---

def _file_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')


def get_file_list(response, cookies, link, title):
    soup = BeautifulSoup(response.text, 'html.parser')
    filelist_section = soup.find(class_='board-filelist')
    if filelist_section is None:
        return []
    try:
        a_tags = filelist_section.find_all('a', href=True)
        file_list = []
        for i, a in enumerate(a_tags):
            name = _get_file_name(a)
            extension = name.split('.')[-1]
            file_list.append({
                'name': name,
                'base64': _download_file(a, cookies, referer=link),
                'code': f'File {chr(65 + i)}.{extension}'
            })
        return file_list
    except Exception as e:
        if str(e) == 'file download error':
            logger.info('file download error, skipping file download')
            error_message = (f'파일 다운로드 에러\n{title}\n'
                             f'{datetime.datetime.now()}\n\n{e}\n\n{traceback.format_exc()}')
            true_email.self_email('snuphya error', error_message)
            return []
        raise


def _get_file_name(a_tag):
    name = a_tag.get_text(strip=True)
    if name:
        return name
    parent = a_tag.parent
    if parent:
        for node in parent.children:
            if isinstance(node, str):
                text = node.strip()
                if text:
                    return text
    return 'unknown_file'


def _download_file(a_tag, cookies, referer=None):
    file_href = a_tag['href']
    file_name = _get_file_name(a_tag)
    file_full_path = f'{FILE_FOLDER}/{file_name}'

    download_url = file_href if file_href.startswith('http') else BASE_URL + file_href
    headers = {'Referer': referer} if referer else {}
    response = requests.get(download_url, cookies=cookies, headers=headers, stream=True)

    if response.status_code != 200:
        raise Exception('file download error')

    with open(file_full_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    logger.info(f'file downloaded: {file_full_path}')
    file_base64 = _file_to_base64(file_full_path)
    os.remove(file_full_path)
    return file_base64


# --- Announcement JSON I/O ---

def save_as_json(dictionary):
    path = f'{ANNOUNCEMENT_FOLDER}/{dictionary["hash"]}.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dictionary, f, indent=4, ensure_ascii=False)


def get_announcement_list():
    parsed_data_list = []
    for filename in os.listdir(ANNOUNCEMENT_FOLDER):
        if filename.endswith('.json'):
            file_path = os.path.join(ANNOUNCEMENT_FOLDER, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    parsed_data_list.append(json.load(f))
            except json.JSONDecodeError:
                logger.error(f"'{filename}' 파일을 파싱하는 중 오류가 발생했습니다.")
                raise
            except IOError:
                logger.error(f"'{filename}' 파일을 읽는 중 오류가 발생했습니다.")
                raise
    return parsed_data_list


def get_not_processed_announcement_list():
    return [a for a in get_announcement_list() if 'batch_id' not in a]


def get_announcement_list_with_specific_batch_id(batch_id):
    return [a for a in get_announcement_list() if a.get('batch_id') == batch_id]


def update_announcement_json_file_with_batch_id(announcement_list, batch_id):
    for announcement in announcement_list:
        announcement['batch_id'] = batch_id
        save_as_json(announcement)


def remove_announcement_json(announcement):
    path = f'{ANNOUNCEMENT_FOLDER}/{announcement["hash"]}.json'
    os.remove(path)
