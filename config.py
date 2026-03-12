import os
from pathlib import Path

import openai
from dotenv import load_dotenv

load_dotenv()

CURRENT_PATH = f'{Path(__file__).resolve().parent}/'
DB_PATH = f'{CURRENT_PATH}checked_items.db'
ANNOUNCEMENT_FOLDER = f'{CURRENT_PATH}announcement_folder'
JSONL_FOLDER = f'{CURRENT_PATH}jsonl_file_folder'
IMAGE_FOLDER = f'{CURRENT_PATH}image'
FILE_FOLDER = f'{CURRENT_PATH}file'
COOKIE_FILE = f'{CURRENT_PATH}cookies.json'

BASE_URL = 'https://physics.snu.ac.kr'

ANNOUNCEMENT_URLS = [
    f'{BASE_URL}/intranet/index.php?mid=board&pid=board&bbsid=graduate&sc=y',
    f'{BASE_URL}/intranet/index.php?mid=board&pid=board&bbsid=graduate&page=2',
    f'{BASE_URL}/intranet/index.php?mid=board&pid=board&bbsid=undergraduate&sc=y',
    f'{BASE_URL}/intranet/index.php?mid=board&pid=board&bbsid=undergraduate&page=2',
]

MAX_DRIVER_RETRIES = 3
MAX_FILE_DOWNLOAD_WAIT = 60
MAX_TEXT_FETCH_RETRIES = 20
MAX_PING_RETRIES = 5
LOOP_SLEEP_SECONDS = 180


def ensure_directories():
    for folder in [ANNOUNCEMENT_FOLDER, JSONL_FOLDER, IMAGE_FOLDER, FILE_FOLDER]:
        os.makedirs(folder, exist_ok=True)


def get_openai_client():
    api_key = os.getenv('OPENAI_API_KEY_SNUPHYA')
    return openai.OpenAI(api_key=api_key)
