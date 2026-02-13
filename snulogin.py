import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import selenium.common.exceptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import chromedriver_autoinstaller
import os
from selenium.webdriver.common.alert import Alert
import imaplib
import email
import datetime
import re
from email.utils import parsedate_to_datetime
import pytz
from bs4 import BeautifulSoup
import requests
from dotenv import load_dotenv

load_dotenv()


def get_linux_driver():
    # 크롬 드라이버
    chrome_ver = chromedriver_autoinstaller.get_chrome_version().split('.')[0]  # 크롬 버전 확인
    chrome_option = webdriver.ChromeOptions()
    chrome_option.add_argument("--headless=new")
    chrome_option.add_argument('--no-sandbox')
    chrome_option.add_argument('--disable-dev-shm-usage')
    chrome_option.add_argument('--disable-browser-side-navigation')
    try:
        s = Service(f'/{chrome_ver}/chromedriver')
        driver_ = webdriver.Chrome(service=s, options=chrome_option)
    except selenium.common.exceptions.WebDriverException:
        chromedriver_autoinstaller.install(True)
        s = Service(f'/{chrome_ver}/chromedriver')
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


def get_driver():
    try:
        return get_linux_driver()
    except selenium.common.exceptions.WebDriverException:
        return get_win_driver()


def snu_login(driver):
    try:
        requests.get(os.getenv('HEALTHCHECK_SNUPHYA_INTRANET') + '/start', timeout=10)
    except requests.RequestException as e:
        print("Ping failed: %s" % e)
    wait = WebDriverWait(driver, 10)
    button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[data-authtype="id"]')))
    button.click()

    driver.find_element(By.ID, 'user_id').send_keys(os.environ.get('SNU_ID'))
    driver.find_element(By.ID, 'user_passwd').send_keys(os.environ.get('SNU_PASSWORD'))

    wait = WebDriverWait(driver, 10)
    button = wait.until(EC.element_to_be_clickable((By.ID, 'btn-id-request')))
    button.click()
    
    time.sleep(1)

    # 현재 시간을 timezone-aware로 변환
    now = datetime.datetime.now(pytz.utc)

    try:
        wait = WebDriverWait(driver, 10)
        button = wait.until(EC.element_to_be_clickable((By.ID, 'btn-send-authcode')))
        button.click()
    except selenium.common.exceptions.TimeoutException:
        req = driver.page_source
        soup_ = BeautifulSoup(req, 'html.parser')
        if '처리 중 오류가 발생하였습니다.' in soup_.text:
            try:
                requests.get(os.getenv('HEALTHCHECK_SNUPHYA_INTRANET') + '/fail', timeout=10)
            except requests.RequestException as e:
                print("Ping failed: %s" % e)
            raise Exception('SNU server error')
    click_alert(driver)

    authcode = get_authcode(now)
    driver.find_element(By.ID, 'id_crtfc_no').send_keys(authcode)

    driver.find_element(By.ID, 'btn-id-auth-submit').click()

    time.sleep(5)

    try:
        requests.get(os.getenv('HEALTHCHECK_SNUPHYA_INTRANET'), timeout=10)
    except requests.RequestException as e:
        print("Ping failed: %s" % e)


def click_alert(driver):
    for _ in range(10):
        time.sleep(1)
        try:
            alert = Alert(driver)
            alert.accept()
            time.sleep(1)
            return
        except selenium.common.exceptions.NoAlertPresentException:
            continue
    raise Exception('cannot click alert')


def get_authcode(now):
    for _ in range(30):
        try:
            code = check_email(now)
            return code
        except Exception as e:
            print(e)
            time.sleep(5)
            continue
    raise Exception('Cannot find authcode')


def extract_verification_code(body):
    # 본문에서 '인증코드 : [코드]' 패턴을 찾습니다.
    match = re.search(r'인증코드\s*:\s*\[([A-Z0-9]+)\]', body)
    if match:
        return match.group(1)
    return None

def check_email(now):
    # 이메일 서버 설정
    IMAP_SERVER = 'imap.gmail.com'
    IMAP_PORT = 993

    # 이메일 계정 정보 입력
    email_address = os.getenv('SNU_GMAIL_EMAIL_ADDRESS')
    password = os.getenv('SNU_GMAIL_PASSWORD')

    # IMAP 클라이언트 인스턴스 생성
    imap_client = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)

    # 이메일 서버에 로그인
    imap_client.login(email_address, password)

    # INBOX 선택
    imap_client.select('Inbox')

    # 이메일 검색 (제목에 "[서울대학교] 인증코드(Verification Code)" 포함)
    keyword = 'Verification Code'

    today = datetime.date.today()
    today_str = today.strftime('%d-%b-%Y')

    # CHARSET을 사용하지 않고 제목 그대로 검색
    status, response = imap_client.search(None, f'(HEADER Subject "{keyword}" SINCE "{today_str}")')

    if status == 'OK' and response[0]:
        # 검색된 이메일의 ID 가져오기
        email_ids = response[0].split()

        for email_id in reversed(email_ids):  # 최신 이메일부터 처리
            # 이메일의 실제 데이터를 가져옴
            status, msg_data = imap_client.fetch(email_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    # 이메일의 수신 날짜 가져오기
                    email_date = msg['Date']
                    email_datetime = parsedate_to_datetime(email_date)

                    # 현재 시간과 이메일 수신 시간의 차이 계산
                    time_diff = now - email_datetime
                    if time_diff.total_seconds() <= 0:
                        # 이메일 본문에서 인코딩된 부분을 처리함
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == 'text/plain':
                                    body = part.get_payload(decode=True).decode(part.get_content_charset())
                                    # 본문에서 인증코드 추출
                                    code = extract_verification_code(body)
                                    if code:
                                        imap_client.logout()
                                        return code
                        else:
                            body = msg.get_payload(decode=True).decode(msg.get_content_charset())
                            # 본문에서 인증코드 추출
                            code = extract_verification_code(body)
                            if code:
                                imap_client.logout()
                                return code

    # IMAP 클라이언트 종료
    imap_client.logout()
    raise Exception('No authcode found')


if __name__ == '__main__':
    driver = get_driver()
    driver.get(url='https://physics.snu.ac.kr/intranet/')
    snu_login(driver)
    time.sleep(50000)
