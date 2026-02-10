import json
import random
import smtplib
import jsonlines
import os
import datetime
import openai
from true_email import true_email
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import selenium.common.exceptions
import chromedriver_autoinstaller
from html2text import html2text
import snulogin
from requests.cookies import cookiejar_from_dict
import requests
import base64
import time
import xxhash
import shutil
import traceback
from pydantic import BaseModel, Field
from true_line import true_line
from todoist_api_python.api import TodoistAPI
import sqlite3


def get_current_path():
    folder_path = '/home/pi/snuphya/'
    folder_exists = os.path.exists(folder_path)
    if folder_exists:
        return folder_path
    else:
        return ''

        
def update_announcement():
    def get_db_path():
        DB_FILENAME = 'checked_items.db'
        return f"{get_current_path()}{DB_FILENAME}"


    def init_db():
        db_path = get_db_path()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checked_items (
                    hash_value TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TEXT
                )
            ''')
            conn.commit()


    def update_checked_item_list(hash_value, title):
        init_db()
        
        current_time = datetime.datetime.now().isoformat()
        db_path = get_db_path()
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO checked_items (hash_value, title, created_at)
                    VALUES (?, ?, ?)
                ''', (hash_value, title, current_time))
                conn.commit()
            except sqlite3.Error as e:
                print(f"데이터베이스 에러 발생: {e}")
                raise


    def is_checked(hash_value):
        init_db()
        db_path = get_db_path()
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM checked_items WHERE hash_value = ?', (hash_value,))
            result = cursor.fetchone()
            
        return result is not None


    def get_checked_item_list():
        """
        저장된 모든 아이템 리스트를 반환합니다 (디버깅/확인용).
        """
        init_db()
        db_path = get_db_path()
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT hash_value, title, created_at FROM checked_items')
            rows = cursor.fetchall()
            
        return rows

    def get_xxh3_128(string):
        """
        문자열을 입력받아 XXH3 128비트 해시값(Hex)을 반환하는 함수
        """
        byte_string = string.encode('utf-8')
        hash_object = xxhash.xxh3_128(byte_string)
        hash_value = hash_object.hexdigest()

        return hash_value

    def get_driver():
        def get_linux_driver():
            chrome_option = webdriver.ChromeOptions()
            chrome_option.add_argument("--headless")
            chrome_option.add_argument('--no-sandbox')
            chrome_option.add_argument('--disable-dev-shm-usage')
            chrome_option.add_argument('--disable-browser-side-navigation')

            # Chromium 브라우저 경로 지정
            chrome_option.binary_location = '/usr/bin/chromium-browser'

            # 수동으로 Chromedriver 경로 지정
            chromedriver_path = '/usr/lib/chromium-browser/chromedriver'

            s = Service(chromedriver_path)
            driver_ = webdriver.Chrome(service=s, options=chrome_option)
            driver_.implicitly_wait(20)
            return driver_

        def get_win_driver():
            # 크롬 드라이버
            chrome_ver = chromedriver_autoinstaller.get_chrome_version().split('.')[0]  # 크롬 버전 확인

            try:
                s = Service(f'./{chrome_ver}/chromedriver.exe')
                driver_ = webdriver.Chrome(service=s)
            except selenium.common.exceptions.WebDriverException:
                chromedriver_autoinstaller.install(True)
                s = Service(f'./{chrome_ver}/chromedriver.exe')
                driver_ = webdriver.Chrome(service=s)
            driver_.implicitly_wait(20)
            return driver_

        try:
            return get_linux_driver()
        except selenium.common.exceptions.WebDriverException:
            return get_win_driver()

    def get_soup(driver_):
        req = driver_.page_source
        soup_ = BeautifulSoup(req, 'html.parser')
        return soup_

    def get_url():
        grad_announcement_url = 'https://physics.snu.ac.kr/intranet/index.php?mid=board&pid=board&bbsid=graduate&sc=y'
        grad_announcement_page2_url = 'https://physics.snu.ac.kr/intranet/index.php?mid=board&pid=board&bbsid=graduate&page=2'
        undergrad_announcement_url = 'https://physics.snu.ac.kr/intranet/index.php?mid=board&pid=board&bbsid=undergraduate&sc=y'
        undergrad_announcement_page2_url = 'https://physics.snu.ac.kr/intranet/index.php?mid=board&pid=board&bbsid=undergraduate&page=2'
        return grad_announcement_url, grad_announcement_page2_url, undergrad_announcement_url, undergrad_announcement_page2_url
        # return grad_announcement_url,

    def get_online_announcement_list(soup_):
        table = soup_.find('tbody')
        rows = table.find_all('tr')
        return rows

    def get_title(row):
        title_ = row.find('span')
        title_ = title_.string
        return title_

    def get_view_count(row):
        return int(row.find_all('td')[-2].get_text(strip=True))

    def get_link(row):
        link_ = row.a['href']
        link_ = 'https://physics.snu.ac.kr' + link_
        return link_

    def get_text(cookies_, link_):
        for i_ in range(20):
            response = requests.get(link_, cookies=cookies_)
            soup_ = BeautifulSoup(response.text, 'html.parser')
            soup_ = soup_.find(class_='board-content clearfix')
            if soup_ is not None:
                return html2text(str(soup_))
        raise Exception('reached maximum iteration')

    def save_as_json(dictionary_):
        current_path = get_current_path()
        with open(f'{current_path}announcement_folder/{dictionary_["hash"]}.json', 'w', encoding='utf-8') as f:
            json.dump(dictionary_, f, indent=4, ensure_ascii=False)

    def get_image_url(body_):
        pattern = r'\(([^()]*\.(?:png|jpg|PNG|JPG))\)'
        matches = re.findall(pattern, body_)
        url_list = matches
        url_list = [f'https://physics.snu.ac.kr{url}' for url in url_list]
        return url_list

    def download_image(img_url_, cookies_):
        # requests 세션 생성 및 쿠키 설정
        session = requests.Session()
        session.cookies = cookiejar_from_dict(cookies_)

        # 이미지 다운로드
        image_type = img_url_.split('.')[-1]
        image_path = f"{get_current_path()}image/image.{image_type}"
        response = session.get(img_url_)
        if response.status_code == 200:
            with open(image_path, "wb") as file:
                file.write(response.content)
            print(f"image downloaded: {image_path}")

            # 이미지를 base64로 인코딩
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                return encoded_image
        else:
            print("이미지 다운로드 실패")
            return False

    def prepare_driver():
        driver_ = get_driver()
        driver_.get(url='https://physics.snu.ac.kr/intranet/')
        snulogin.snu_login(driver_)
        return driver_

    def get_file_list(announcement_, driver_):
        def generate_file_code():
            if not hasattr(generate_file_code, "count"):
                generate_file_code.count = 0
            letter = chr(65 + generate_file_code.count)
            generate_file_code.count += 1
            return f"File {letter}"

        driver_.get(get_link(announcement_))
        soup_ = get_soup(driver_)
        soup_ = soup_.find(class_='board-filelist')
        if soup_ is None:
            return []
        try:
            file_list_ = [{'name': a.get_text(strip=True),
                        'base64': download_file(a, driver_),
                        'code': f'{generate_file_code()}.{a.get_text(strip=True).split(".")[-1]}'
                        } for a in soup_.find_all('a', href=True)]
        except Exception as e:
            if str(e) == 'file download error':
                print('file download error, skipping file download')
                error_title = get_title(announcement_)
                error_message = f'파일 다운로드 에러\n{error_title}\n{datetime.datetime.now()}\n\n{e}\n\n{traceback.format_exc()}'
                true_email.self_email('snuphya error', error_message)
                return []
            raise
        return file_list_

    def download_file(a_tag, driver_):
        def convert_to_base64(given_path):
            with open(given_path, "rb") as file_:
                encoded_file = base64.b64encode(file_.read()).decode('utf-8')
                return encoded_file
        file_href_ = a_tag['href']
        file_name_ = a_tag.get_text(strip=True)
        download_button = driver_.find_element(By.CSS_SELECTOR, f"a[href='{file_href_}']")
        download_button.click()
        count_ = 0
        while not os.path.exists(file_name_):
            count_ += 1
            time.sleep(1)
            if count_ > 60:
                raise Exception('file download error')
        file_path = shutil.move(file_name_, fr'{get_current_path()}file/{file_name_}')
        print(f'file downloaded: {file_path}')
        file_base64 = convert_to_base64(file_path)
        os.remove(file_path)
        return file_base64

    def need_to_be_checked(row):
        title_hash = get_title(row)
        title_hash = get_xxh3_128(title_hash)
        if not is_checked(title_hash):
            return True
        date_str = row.find_all('td')[-1].get_text(strip=True)
        date_datetime = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if date_datetime.date() == datetime.datetime.today().date():
            return True
        if random.random() < 1 / 5:
            return True
        return False

    max_try = 3
    for i in range(1, max_try + 1):
        try:
            driver = prepare_driver()
            break
        except Exception:
            if i == max_try:
                raise
            continue
    time.sleep(3)

    announcement_list = []
    for announcement_page_url in get_url():
        driver.get(url=announcement_page_url)
        soup = get_soup(driver)
        announcement_list += get_online_announcement_list(soup)

    for announcement in announcement_list:  # 여기에서 각 공지사항으로 json 파일 만들기. hash, title, body, image 등등
        if not need_to_be_checked(announcement):
            continue
        title = get_title(announcement)
        print(title)
        link = get_link(announcement)
        view_count = get_view_count(announcement)
        cookies = driver.get_cookies()
        cookies = {cookie['name']: cookie['value'] for cookie in cookies}
        body = get_text(cookies, link)
        now = datetime.datetime.now()
        now = str(now)

        announcement_hash = title + body
        announcement_hash = get_xxh3_128(announcement_hash)
        if is_checked(announcement_hash):
            continue

        # announcement_dictionary = {'hash': announcement_hash,
        #                            'title': title,
        #                            'body': body,
        #                            'link': link,
        #                            'check_time': now,
        #                            'view_count': view_count}

        # if '![](/webdata/upimages' in body:
        #     image_url_list = get_image_url(body)
        #     image_code_list = [download_image(image_url, cookies) for image_url in image_url_list]

        #     announcement_dictionary['image_code'] = image_code_list

        # file_list = get_file_list(announcement, driver)
        # announcement_dictionary['file'] = file_list

        # save_as_json(announcement_dictionary)
        update_checked_item_list(get_xxh3_128(title), title)
        update_checked_item_list(announcement_hash, title)

    result = get_checked_item_list()
    for row in result:
        print(row)


def init_db():
        db_path = get_db_path()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checked_items (
                    hash_value TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TEXT
                )
            ''')
            conn.commit()


def get_db_path():
        DB_FILENAME = 'checked_items.db'
        return f"{get_current_path()}{DB_FILENAME}"


def delete_item_by_title(title):
    """
    주어진 제목(title)을 가진 데이터를 데이터베이스에서 삭제합니다.
    삭제된 행(row)의 개수를 반환합니다.
    """
    init_db()
    db_path = get_db_path()
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        try:
            # 제목이 일치하는 항목 삭제 쿼리 실행
            cursor.execute('DELETE FROM checked_items WHERE title = ?', (title,))
            conn.commit()
            
            # 삭제된 행의 개수 확인 (0이면 삭제된 것이 없음)
            deleted_count = cursor.rowcount
            return deleted_count
            
        except sqlite3.Error as e:
            print(f"데이터 삭제 중 에러 발생: {e}")
            raise


if __name__ == '__main__':
    update_announcement()