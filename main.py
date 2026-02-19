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
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def get_openai_client(image=False):
    image_description_api_key = os.getenv('OPENAI_API_KEY_SNUPHYA')
    client = openai.OpenAI(api_key=image_description_api_key)
    return client


def get_current_path():
    return f'{Path(__file__).resolve().parent}/'


def ensure_directories():
    current_path = get_current_path()
    for folder in ['announcement_folder', 'jsonl_file_folder', 'image', 'file']:
        os.makedirs(f'{current_path}{folder}', exist_ok=True)


def get_announcement_list():  # 모든 "공지 dictionary"가 담겨있는 list 반환
    parsed_data_list = []
    announcement_folder_path = f'{get_current_path()}announcement_folder'
    for filename in os.listdir(announcement_folder_path):
        if filename.endswith('.json'):
            file_path = os.path.join(announcement_folder_path, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    parsed_data = json.load(f)
                    parsed_data_list.append(parsed_data)
            except json.JSONDecodeError:
                print_and_log(f"'{filename}' 파일을 파싱하는 중 오류가 발생했습니다.")
                raise
            except IOError:
                print_and_log(f"'{filename}' 파일을 읽는 중 오류가 발생했습니다.")
                raise
    # print_and_log(f'every announcement list: {parsed_data_list}')
    return parsed_data_list


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
                print_and_log(f"데이터베이스 에러 발생: {e}")
                raise


    def is_checked(hash_value):
        init_db()
        db_path = get_db_path()
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM checked_items WHERE hash_value = ?', (hash_value,))
            result = cursor.fetchone()
            
        return result is not None


    def get_xxh3_128(string):
        """
        문자열을 입력받아 XXH3 128비트 해시값(Hex)을 반환하는 함수
        """
        byte_string = string.encode('utf-8')
        hash_object = xxhash.xxh3_128(byte_string)
        hash_value = hash_object.hexdigest()

        return hash_value

    def get_driver():
        chrome_option = webdriver.ChromeOptions()
        chrome_option.add_argument("--headless")
        chrome_option.add_argument('--window-size=1920,1080')
        chrome_option.add_argument('--no-sandbox')
        chrome_option.add_argument('--disable-dev-shm-usage')
        chrome_option.add_argument('--disable-browser-side-navigation')

        chrome_option.binary_location = os.getenv('CHROMIUM_PATH')
        chromedriver_path = os.getenv('CHROME_DRIVER_PATH')

        s = Service(chromedriver_path)
        driver_ = webdriver.Chrome(service=s, options=chrome_option)
        driver_.implicitly_wait(20)
        return driver_

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
            print_and_log(f"image downloaded: {image_path}")

            # 이미지를 base64로 인코딩
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
                return encoded_image
        else:
            print_and_log("이미지 다운로드 실패")
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
                print_and_log('file download error, skipping file download')
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
        print_and_log(f'file downloaded: {file_path}')
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

    try:
        finish_loop = False
        inner_loop_first_time = True
        while datetime.datetime.now().minute % 30 < 25 or inner_loop_first_time:
            inner_loop_first_time = False
            announcement_list = []
            for announcement_page_url in get_url():
                driver.get(url=announcement_page_url)
                soup = get_soup(driver)
                announcement_list += get_online_announcement_list(soup)

            for announcement in announcement_list:  # 여기에서 각 공지사항으로 json 파일 만들기. hash, title, body, image 등등
                if not need_to_be_checked(announcement):
                    continue
                title = get_title(announcement)
                print_and_log(title)
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

                announcement_dictionary = {'hash': announcement_hash,
                                        'title': title,
                                        'body': body,
                                        'link': link,
                                        'check_time': now,
                                        'view_count': view_count}

                if '![](/webdata/upimages' in body:
                    image_url_list = get_image_url(body)
                    image_code_list = [download_image(image_url, cookies) for image_url in image_url_list]

                    announcement_dictionary['image_code'] = image_code_list

                file_list = get_file_list(announcement, driver)
                announcement_dictionary['file'] = file_list

                save_as_json(announcement_dictionary)
                update_checked_item_list(get_xxh3_128(title), f'{title}; title')
                update_checked_item_list(announcement_hash, f'{title}; body')
                finish_loop = True
            if finish_loop:
                return
            if datetime.datetime.now().minute % 30 < 25:
                print_and_log('waiting for next announcement check loop')
                time.sleep(180)
    except Exception as e:
        print_and_log(f'exception occurred while checking announcements\n{e}')
        return


def get_not_processed_announcement_list():  # 아직 batch 작업 들어가지 않은 공지사항 dictionary가 담겨있는 list 반환
    announcement_list = get_announcement_list()
    redendum_not_processed_announcement_list = []
    for each_announcement in announcement_list:
        if 'batch_id' not in each_announcement.keys():
            redendum_not_processed_announcement_list.append(each_announcement)
    return redendum_not_processed_announcement_list


def generate_each_line_of_batch_file(announcement):  # jsonl 파일의 각 줄을 만드는 함수
    system_message = '''당신은 공지사항을 요약하는 전문가입니다. 공지사항 본문을 분석하여 3문장 이하로 요약하세요. 각 문장은 번호를 매기세요. 모든 응답은 한국어로 작성하세요. 단, 전문 용어는 다른 언어를 사용해도 됩니다.

# Steps

1. 주어진 공지사항 제목과 본문을 철저히 분석하세요.
2. 본문에서 핵심 정보를 식별하고 추출합니다.
3. 식별된 정보를 바탕으로 요약 문장을 작성하세요.
4. 각 요약 문장을 번호로 구분합니다.

# Output Format

- 3문장 이하로 구성된 문장 목록, 각 문장은 번호가 매겨짐

# Examples

**Input:** 
```
제목: [반도체특성화대학] 반도체 소자 워크샵 참여 모집 공고
본문: 안녕하세요, 반도체특성화대학입니다.

장학생 여러분 중 반도체 소자 워크숍에 참여할 인원을 조사합니다.

관심 있으신 분들의 많은 지원 부탁드리며, 의무사항은 아니니 참고 부탁드립니다.

특강 교재는 무료로 제공됩니다.

행사 일정: 2025년 2월 14일 (금요일) 오후 1시 ~ 4시 (3시간)
특강 내용: 트랜지스터의 기본 원리, NAND Flash의 동작 원리, 실제 소자 (MOS, FeNAND) 측정
행사 장소: 반도체공동연구소 (104동) 도연홀 및 제1 측정교육실

구글 폼 작성은 2025년 1월 20일 오후 1시까지이니, 기한 맞춰 작성 부탁드리겠습니다.

구글 폼 링크: https://forms.gle/231oETLmDik2CHXA6

감사합니다.

반도체특성화대학 드림
```

**Output:**
1. 반도체특성화대학에서 반도체 소자 워크숍에 참여할 장학생을 모집하며, 의무사항은 아닙니다.
2. 워크숍은 2025년 2월 14일 오후 1시부터 4시까지 반도체공동연구소 도연홀 및 제1 측정교육실에서 진행됩니다.
3. 참여 희망자는 2025년 1월 20일 오후 1시까지 구글 폼을 작성해야 합니다.

# Notes

- 전문용어는 다른 언어를 사용할 수 있으니, 적절히 활용하세요.
- 정보를 정확히 요약하여 잘못된 해석이 없도록 주의하세요.'''
    message = f'제목: {announcement["title"]}\n본문: {announcement["body"]}'
    include_image = ('image_code' in announcement)
    if include_image:
        image_code_list = announcement['image_code']
        final_user_message = [{"type": "text", "text": message}]
        for each_image_code in image_code_list:
            final_user_message.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{each_image_code}"}})
    else:
        final_user_message = message
    fuit_json = {"custom_id": announcement['hash'],
                 "method": "POST",
                 "url": "/v1/chat/completions",
                 "body": {
                     "messages": [{"role": "system", "content": system_message},
                                  {"role": "user", "content": final_user_message}],
                     "max_tokens": 500, "temperature": 0.3,
                     "model": "gpt-4.1-nano"}}
    return fuit_json


def generate_batch_file_with_announcement_list(announcement_list):  # batch 작업 들어가지 않은 이메일 list를 주면 batch 파일 만드는 함수
    jsonl_data = [generate_each_line_of_batch_file(each_announcement) for each_announcement in announcement_list]

    jsonl_file_name = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    jsonl_file_path = f"{get_current_path()}jsonl_file_folder/{jsonl_file_name}.jsonl"
    with jsonlines.open(jsonl_file_path, mode="w") as writer:
        writer.write_all(jsonl_data)
    print_and_log(f'generated batch file: {jsonl_file_path}')
    return jsonl_file_path


def start_processing_batch_file(batch_file_path):  # batch 파일을 주면 작업 시작하는 함수
    batch_input_file = upload_batch_file(batch_file_path)

    client = get_openai_client()

    batch_input_file_id = batch_input_file.id
    batch = client.batches.create(
        input_file_id=batch_input_file_id,
        endpoint="/v1/chat/completions",
        completion_window="24h"
    )
    return batch


def upload_batch_file(batch_file_name):
    client = get_openai_client()
    batch_input_file = client.files.create(
        file=open(batch_file_name, "rb"),
        purpose="batch"
    )
    os.remove(batch_file_name)
    return batch_input_file


def get_batch_object_with_id(batch_id):
    client = get_openai_client()
    batch = client.batches.retrieve(batch_id)
    return batch


def get_batch_result(batch_id):
    batch = get_batch_object_with_id(batch_id)
    if batch.status == 'completed':
        if batch.request_counts.completed == 0:
            raise Exception('failed')
        output_file_id = batch.output_file_id
        client = get_openai_client()
        file_response = client.files.content(output_file_id)
        good_result = file_response.text
        if batch.request_counts.failed == 0:
            final_return = good_result
        else:
            error_file_id = batch.error_file_id
            file_response = client.files.content(error_file_id)
            bad_result = file_response.text
            final_return = good_result + bad_result
        return final_return
    elif batch.status in ['validating', 'in_progress', 'finalizing']:
        raise Exception('in progress')
    elif batch.status in ['failed', 'expired', 'cancelling', 'cancelled']:
        raise Exception('failed')
    else:
        raise Exception('unexpected error')


def convert_batch_result_into_readable_form(batch_result):
    batch_result = [json.loads(line) for line in batch_result.splitlines()]
    readable_batch_result = []
    for each_batch_result in batch_result:
        if each_batch_result['response']['status_code'] == 200:
            each_final_answer = each_batch_result["response"]["body"]["choices"][0]["message"]["content"]
        else:
            each_final_answer = '요약 중 오류 발생'
        readable_batch_result.append((each_batch_result['custom_id'], each_final_answer))
    return readable_batch_result


def update_announcement_json_file_with_batch_id(processed_announcement_list,
                                                batch_id):  # batch 작업 들어간 공지사항에 batch id 추가
    current_path = get_current_path()
    for each_announcement in processed_announcement_list:
        each_announcement['batch_id'] = batch_id
        with open(f'{current_path}announcement_folder/{each_announcement["hash"]}.json', 'w', encoding='utf-8') as f:
            json.dump(each_announcement, f, indent=4, ensure_ascii=False)


def delete_line_from_file(file_path, line_to_delete):
    with open(file_path, 'r', encoding='UTF-8') as file:
        lines = file.readlines()

    new_lines = [line for line in lines if line.strip() != line_to_delete.strip()]

    with open(file_path, 'w', encoding='UTF-8') as file:
        file.writelines(new_lines)


def get_processing_batch_list():
    current_path = get_current_path()
    try:
        f = open(f'{current_path}processing batch list.txt', 'r', encoding='UTF-8')
    except FileNotFoundError:
        f = open(f'{current_path}processing batch list.txt', 'w', encoding='UTF-8')
        f.close()
        return list()
    try:
        processing_item_list_ = f.readlines()
    finally:
        f.close()
    return [processing_item.strip() for processing_item in processing_item_list_]


def update_processing_batch_list(text_):
    current_path = get_current_path()
    f = open(f'{current_path}processing batch list.txt', 'a', encoding='UTF-8')
    try:
        f.write(text_)
        f.write('\n')
    finally:
        f.close()


def start_batch():
    procedendum_announcement_list = get_not_processed_announcement_list()
    if not procedendum_announcement_list:
        print_and_log('no procedendum announcement')
        return
    jsonl_file_path = generate_batch_file_with_announcement_list(procedendum_announcement_list)
    batch = start_processing_batch_file(jsonl_file_path)
    batch_id = batch.id
    update_processing_batch_list(batch_id)
    update_announcement_json_file_with_batch_id(procedendum_announcement_list, batch_id)
    return batch_id


def get_announcement_list_with_specific_batch_id(batch_id):
    announcement_list = get_announcement_list()
    redendum_announcement_list = []
    for each_announcement in announcement_list:
        try:
            if each_announcement['batch_id'] == batch_id:
                redendum_announcement_list.append(each_announcement)
        except KeyError:
            continue
    return redendum_announcement_list


def check_processing_batch(new_batch_):
    def make_email_subject(given_announcement, include_header=True):
        link = given_announcement['link']
        title = given_announcement['title']
        if 'id=undergraduate' in link:
            subject = f'{"[물천인트라넷]" if include_header else ""}[학부] {title}'
        elif 'id=graduate' in link:
            subject = f'{"[물천인트라넷] " if include_header else ""}{title}'
        else:
            subject = f'{"[물천인트라넷]" if include_header else ""}[?] {title}'
        return subject

    batch_list = get_processing_batch_list()
    new_left_batch = []
    for each_batch in batch_list:
        try:
            batch_result = get_batch_result(batch_id=each_batch)
        except Exception as e_:
            e_ = str(e_)
            if e_ == 'in progress':
                print_and_log(f'{each_batch} in progress')
                if each_batch == new_batch_:
                    new_left_batch.append(each_batch)
                continue
            elif e_ == 'failed':
                failed_announcement_list = get_announcement_list_with_specific_batch_id(each_batch)

                for each_failed_announcement in failed_announcement_list:
                    print_and_log(f'{each_failed_announcement["title"]} 요약 실패')
                    final_subject = make_email_subject(each_failed_announcement)
                    final_body = (f'요약 전체 실패\n\n\n{each_failed_announcement["body"]}\n\n'
                                  f'확인 시간: {each_failed_announcement["check_time"]}\n'
                                  f'조회수: {each_failed_announcement["view_count"]}\n')
                    for each_file in each_failed_announcement['file']:
                        final_body += f'{each_file["code"]}: {each_file["name"]}\n'
                    try:
                        if 'image_code' in each_failed_announcement and each_failed_announcement['image_code']:
                            true_email.self_email(final_subject, final_body,
                                                  each_failed_announcement['image_code'][0],
                                                  each_failed_announcement['file'])
                        else:
                            true_email.self_email(final_subject, final_body, None,
                                                  each_failed_announcement['file'])
                    except smtplib.SMTPSenderRefused:
                        true_email.self_email(final_subject, f'{final_body}\n첨부파일 건너뜀')

                    if related_to_grad_school(each_failed_announcement):
                        add_todolist(make_email_subject(each_failed_announcement, include_header=False), f'조회수: {each_failed_announcement["view_count"]}\n확인 시간: {each_failed_announcement["check_time"]}')

                delete_line_from_file(f'{get_current_path()}processing batch list.txt', each_batch)
                for each_failed_announcement in failed_announcement_list:
                    os.remove(f"{get_current_path()}announcement_folder/{each_failed_announcement['hash']}.json")
                continue
            else:
                raise
        readable_batch_result = convert_batch_result_into_readable_form(batch_result)

        for announcement_hash, announcement_summary in readable_batch_result:
            print_and_log(f'announcement hash: {announcement_hash}')
            file_path = f'{get_current_path()}announcement_folder/{announcement_hash}.json'
            with open(file_path, 'r', encoding='UTF-8') as f:
                announcement_dictionary = json.load(f)
            print_and_log(f'{announcement_dictionary["title"]} 요약 완료')
            final_subject = make_email_subject(announcement_dictionary)
            final_body = (f'{announcement_summary}\n\n{announcement_dictionary["body"]}\n\n'
                          f'확인 시간: {announcement_dictionary["check_time"]}\n'
                          f'조회수: {announcement_dictionary["view_count"]}\n')
            for each_file in announcement_dictionary['file']:
                final_body += f'{each_file["code"]}: {each_file["name"]}\n'
            try:
                if 'image_code' in announcement_dictionary and announcement_dictionary['image_code']:
                    true_email.self_email(final_subject, final_body,
                                          announcement_dictionary['image_code'][0], announcement_dictionary['file'])
                else:
                    true_email.self_email(final_subject, final_body, None, announcement_dictionary['file'])
            except smtplib.SMTPSenderRefused:
                true_email.self_email(final_subject, f'{final_body}\n첨부파일 건너뜀')

            if related_to_grad_school(announcement_dictionary):
                add_todolist(make_email_subject(announcement_dictionary, include_header=False), f'{announcement_summary}\n\n조회수: {announcement_dictionary["view_count"]}\n확인 시간: {announcement_dictionary["check_time"]}')

        delete_line_from_file(f'{get_current_path()}processing batch list.txt', each_batch)
        finished_announcement_list = get_announcement_list_with_specific_batch_id(each_batch)
        for each_announcement in finished_announcement_list:
            os.remove(f"{get_current_path()}announcement_folder/{each_announcement['hash']}.json")
    return new_left_batch


def finalize_processing_batch(new_left_batch):
    announcement_list = []
    for each_batch in new_left_batch:
        announcement_list.extend(get_announcement_list_with_specific_batch_id(each_batch))
    subject = '[물천인트라넷] 요약 진행중'
    body = ''
    for each_announcement in announcement_list:
        body += (f'{each_announcement["title"]}\n\n'
                 f'조회수: {each_announcement["view_count"]}\n'
                 f'확인 시간: {each_announcement["check_time"]}\n'
                 f'링크: {each_announcement["link"]}\n\n\n')
    body += f'\n{"-"*10}\n'
    for each_announcement in announcement_list:
        body += (f'제목: {each_announcement["title"]}\n\n'
                 f'본문:\n{each_announcement["body"]}\n\n\n')
    body = body.strip()
    true_email.self_email(subject, body)


def related_to_grad_school(_announcement):
    link = _announcement['link']
    if 'id=graduate' in link:
        return True
    body = f'{_announcement["title"]}\n{_announcement["body"]}'
    return any(keyword in body for keyword in ['대학원', '대학(원)', '석사', '박사', '석박'])


def check_if_urgent():
    to_be_checked_announcement_list = get_not_processed_announcement_list()
    if not to_be_checked_announcement_list:
        print_and_log('no to-be-checked announcement')
        return
    for each_announcement in to_be_checked_announcement_list:
        if not related_to_grad_school(each_announcement):
            continue
        announcement_subject = each_announcement['title']
        announcement_content = each_announcement['body']
        analysis_result = analyze_announcement_if_urgent(announcement_subject, announcement_content)
        if analysis_result.has_compensation:
            subject = '[물천인트라넷][중요] ' + each_announcement['title']
            body = (f'{each_announcement["body"]}\n\n\n'
                    f'인원 제한: {analysis_result.has_participant_limit}\n\n'
                    f'판단 근거: {analysis_result.reasoning}\n\n'
                    f'확인 시간: {each_announcement["check_time"]}\n'
                    f'조회수: {each_announcement["view_count"]}\n'
                    f'링크: {each_announcement["link"]}\n')
            try:
                if 'image_code' in each_announcement and each_announcement['image_code']:
                    true_email.self_email(subject, body,
                                          each_announcement['image_code'][0], each_announcement['file'])
                else:
                    true_email.self_email(subject, body, None, each_announcement['file'])
            except smtplib.SMTPSenderRefused:
                true_email.self_email(subject, f'{body}\n첨부파일 건너뜀')

            if analysis_result.has_participant_limit:
                line_body = f'{subject}\n\n인원 제한: {analysis_result.has_participant_limit}\n판단 근거: {analysis_result.reasoning}'
                true_line.send_text(line_body)
                add_todolist(each_announcement['title'], f'인원 제한: {analysis_result.has_participant_limit}\n판단 근거: {analysis_result.reasoning}',
                            due_date='in 5 minutes', priority=4)
            else:
                add_todolist(each_announcement['title'], f'인원 제한: {analysis_result.has_participant_limit}\n판단 근거: {analysis_result.reasoning}',
                            due_date='today', priority=2)
                
            os.remove(f"{get_current_path()}announcement_folder/{each_announcement['hash']}.json")


class AnnouncementCheck(BaseModel):
    has_participant_limit: bool = Field(  
        ..., 
        description="공지사항에 '선착순', '00명 모집', '정원 제한', '조기 마감' 등 참여 인원에 물리적인 제한이 있는 경우 True, 아니면 False"
    )
    has_compensation: bool = Field(
        ..., 
        description="공지사항에 인건비, 수당, 급여, 알바비, 참가비 지급 등의 금전적 보상 내용이 포함되어 있으면 True, 아니면 False"
    )
    reasoning: str = Field(
        ..., 
        description="위의 True/False 판단을 내린 근거를 한국어로 한 문장으로 요약"
    )

def analyze_announcement_if_urgent(announcement_subject, announcement_content):
    """
    공지사항 제목과 내용을 분석하여 인원 제한 여부와 인건비 지급 여부를 반환합니다.
    """
    try:
        client = get_openai_client(image=False)

        # 시스템 프롬프트: AI에게 역할을 부여하고 판단 기준을 명확히 합니다.
        system_instruction = (
            "당신은 공지사항을 분석하는 행정 보조 AI입니다. "
            "주어진 제목과 내용을 바탕으로 다음 두 가지를 판단하여 구조화된 데이터로 반환하세요.\n"
            "1. 인원 제한 여부 (선착순, 00명, 조기 마감 등)\n"
            "2. 인건비/수당 지급 여부 (참가비, 수당, 인건비, 급여 제공 등)"
        )

        user_input = (
            f"<제목>\n{announcement_subject}\n</제목>\n\n"
            f"<내용>\n{announcement_content}\n</내용>"
        )

        # Structured Outputs 사용 (client.beta.chat.completions.parse)
        completion = client.beta.chat.completions.parse(
            model="gpt-5-mini-2025-08-07",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_input},
            ],
            response_format=AnnouncementCheck, # Pydantic 모델을 포맷으로 지정
        )

        # 파싱된 결과 객체 가져오기
        result = completion.choices[0].message.parsed
        print_and_log(f'{announcement_subject}\n분석 결과: {result}')
        return result

    except Exception as e:
        print_and_log(f"분석 중 에러 발생: {e}")
        raise


def add_todolist(name, description, due_date='today', priority=1):
    api_token = os.getenv('TODOIST_API_TOKEN')
    api = TodoistAPI(api_token)
    task = api.add_task(
        content=name,
        description=description,
        due_string=due_date,
        priority=priority,
        labels=['물천인트라넷']
    )
    print_and_log(f"작업 생성 성공: {task.content} (ID: {task.id})")


def print_and_log(message):
    global log_lines
    print(message)
    log_lines.append(f'[{datetime.datetime.now().isoformat()}] {message}')


def ping_test(url, message):
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            requests.get(url, data=message.encode('utf-8'), timeout=10)
            return True
        except requests.RequestException as e:
            print_and_log(f"Ping failed (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(attempt)
    print_and_log("All retry attempts exhausted")
    return False

if __name__ == '__main__':
    ensure_directories()
    try:
        first_time = True
        while datetime.datetime.now().minute % 30 < 15 or first_time:
            first_time = False

            log_lines = []
            ping_test(os.getenv('HEALTHCHECK_SNUPHYA') + "/start", "SNUPHYA announcement checker started")

            print_and_log('starting updating announcement')
            try:
                update_announcement()
            except Exception as e:
                print_and_log(f'error occurred while updating announcements: {e}\nretrying')
                update_announcement()
            print_and_log('starting checking urgent announcement')
            check_if_urgent()
            print_and_log('starting batch')
            new_batch = start_batch()
            print_and_log('starting checking processing batch')
            processing_batch = check_processing_batch(new_batch_=new_batch)
            if not processing_batch:
                print_and_log('no batch left')
            else:
                print_and_log('some batches left but terminating')
            log_payload = "\n".join(log_lines)
            ping_test(os.getenv('HEALTHCHECK_SNUPHYA'), log_payload)
            
            if datetime.datetime.now().minute % 30 < 15:
                print_and_log('waiting for next loop')
                time.sleep(180)

    except Exception as e:
        if 'SNU server error' in str(e):
            print_and_log('SNU server error occurred, skipping email notification')

            log_payload = "\n".join(log_lines)
            ping_test(os.getenv('HEALTHCHECK_SNUPHYA'), log_payload)
        else:
            error_message = f'에러 발생함\n{datetime.datetime.now()}\n\n{e}\n\n{traceback.format_exc()}'
            ping_test(os.getenv('HEALTHCHECK_SNUPHYA') + "/fail", error_message)
