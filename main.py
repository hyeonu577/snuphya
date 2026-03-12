import datetime
import json
import logging
import os
import time
import traceback

import requests
from dotenv import load_dotenv

import batch
import cookie_manager
import db
import notifier
import scraper
from config import (
    ANNOUNCEMENT_FOLDER,
    ANNOUNCEMENT_URLS,
    MAX_PING_RETRIES,
    ensure_directories,
)

load_dotenv()

# --- Logging setup ---

logger = logging.getLogger('snuphya')
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())


class LogCollector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(self.format(record))

    def flush_lines(self):
        lines = list(self.records)
        self.records.clear()
        return lines


log_collector = LogCollector()
log_collector.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
logger.addHandler(log_collector)


# --- Orchestration functions ---

def update_announcements():
    cookies = cookie_manager.get_cookies()

    try:
        announcement_list = []
        for url in ANNOUNCEMENT_URLS:
            soup, response = scraper.get_soup_from_url(url, cookies)
            if not cookie_manager.is_session_valid(response):
                logger.info('session expired, re-logging in')
                cookies = cookie_manager.login_and_get_cookies()
                soup, response = scraper.get_soup_from_url(url, cookies)
            announcement_list += scraper.get_online_announcement_list(soup)

        for announcement in announcement_list:
            if not scraper.need_to_be_checked(announcement):
                continue
            title = scraper.get_title(announcement)
            logger.info(title)
            link = scraper.get_link(announcement)
            view_count = scraper.get_view_count(announcement)
            category = scraper.get_category(announcement)
            body = scraper.get_text(cookies, link, title, category)
            now = str(datetime.datetime.now())

            announcement_hash = db.get_xxh3_128(title + body)
            if db.is_checked(announcement_hash):
                continue

            announcement_dict = {
                'hash': announcement_hash,
                'title': title,
                'body': body,
                'link': link,
                'check_time': now,
                'view_count': view_count,
            }

            if '![](/webdata/upimages' in body:
                image_url_list = scraper.get_image_url(body)
                announcement_dict['image_code'] = [
                    scraper.download_image(url, cookies) for url in image_url_list
                ]

            announcement_dict['file'] = scraper.get_file_list(announcement, cookies)

            scraper.save_as_json(announcement_dict)
            db.update_checked_item_list(db.get_xxh3_128(title), f'{title}; title')
            db.update_checked_item_list(announcement_hash, f'{title}; body')
    except cookie_manager.SessionExpiredError:
        logger.info('session expired during processing, re-logging in and retrying')
        cookie_manager.login_and_get_cookies()
        update_announcements()
    except Exception as e:
        logger.info(f'exception occurred while checking announcements\n{e}')
        return


def start_batch():
    announcement_list = scraper.get_not_processed_announcement_list()
    if not announcement_list:
        logger.info('no procedendum announcement')
        return None
    jsonl_file_path = batch.generate_batch_file(announcement_list)
    batch_obj = batch.start_processing_batch_file(jsonl_file_path)
    batch_id = batch_obj.id
    db.add_processing_batch(batch_id)
    scraper.update_announcement_json_file_with_batch_id(announcement_list, batch_id)
    return batch_id


def check_processing_batch(new_batch_):
    batch_list = db.get_processing_batches()
    new_left_batch = []
    for each_batch in batch_list:
        try:
            batch_result = batch.get_batch_result(batch_id=each_batch)
        except Exception as e_:
            e_str = str(e_)
            if e_str == 'in progress':
                logger.info(f'{each_batch} in progress')
                if each_batch == new_batch_:
                    new_left_batch.append(each_batch)
                continue
            elif e_str == 'failed':
                failed_list = scraper.get_announcement_list_with_specific_batch_id(each_batch)
                for announcement in failed_list:
                    logger.info(f'{announcement["title"]} 요약 실패')
                    subject = notifier.make_email_subject(announcement)
                    body = notifier.format_announcement_body(announcement)
                    notifier.send_announcement_email(subject, body, announcement)
                    if notifier.related_to_grad_school(announcement):
                        notifier.add_todolist(
                            notifier.make_email_subject(announcement, include_header=False),
                            f'조회수: {announcement["view_count"]}\n확인 시간: {announcement["check_time"]}')
                db.remove_processing_batch(each_batch)
                for announcement in failed_list:
                    scraper.remove_announcement_json(announcement)
                continue
            else:
                raise

        readable_result = batch.convert_batch_result_into_readable_form(batch_result)
        for announcement_hash, summary in readable_result:
            logger.info(f'announcement hash: {announcement_hash}')
            file_path = f'{ANNOUNCEMENT_FOLDER}/{announcement_hash}.json'
            with open(file_path, 'r', encoding='UTF-8') as f:
                announcement = json.load(f)
            logger.info(f'{announcement["title"]} 요약 완료')
            subject = notifier.make_email_subject(announcement)
            body = notifier.format_announcement_body(announcement, summary=summary)
            notifier.send_announcement_email(subject, body, announcement)
            if notifier.related_to_grad_school(announcement):
                notifier.add_todolist(
                    notifier.make_email_subject(announcement, include_header=False),
                    f'{summary}\n\n조회수: {announcement["view_count"]}\n확인 시간: {announcement["check_time"]}')

        db.remove_processing_batch(each_batch)
        finished_list = scraper.get_announcement_list_with_specific_batch_id(each_batch)
        for announcement in finished_list:
            scraper.remove_announcement_json(announcement)

    return new_left_batch


def ping_test(url, message):
    for attempt in range(1, MAX_PING_RETRIES + 1):
        try:
            requests.get(url, data=message.encode('utf-8'), timeout=10)
            return True
        except requests.RequestException as e:
            logger.info(f"Ping failed (attempt {attempt}/{MAX_PING_RETRIES}): {e}")
            if attempt < MAX_PING_RETRIES:
                time.sleep(attempt)
    logger.info("All retry attempts exhausted")
    return False


if __name__ == '__main__':
    ensure_directories()
    db.init_db()
    try:
        log_collector.flush_lines()
        ping_test(os.getenv('HEALTHCHECK_SNUPHYA') + "/start",
                  "SNUPHYA announcement checker started")

        logger.info('starting updating announcement')
        try:
            update_announcements()
        except Exception as e:
            logger.info(f'error occurred while updating announcements: {e}\nretrying')
            update_announcements()

        logger.info('starting checking urgent announcement')
        urgent_list = scraper.get_not_processed_announcement_list()
        for announcement in notifier.check_if_urgent(urgent_list):
            scraper.remove_announcement_json(announcement)

        logger.info('starting batch')
        new_batch = start_batch()
        logger.info('starting checking processing batch')
        processing_batch = check_processing_batch(new_batch_=new_batch)
        if not processing_batch:
            logger.info('no batch left')
        else:
            logger.info('some batches left but terminating')

        log_payload = "\n".join(log_collector.flush_lines())
        ping_test(os.getenv('HEALTHCHECK_SNUPHYA'), log_payload)

    except Exception as e:
        if 'SNU server error' in str(e):
            logger.info('SNU server error occurred, skipping email notification')
            log_payload = "\n".join(log_collector.flush_lines())
            ping_test(os.getenv('HEALTHCHECK_SNUPHYA'), log_payload)
            raise
        else:
            error_message = f'에러 발생함\n{datetime.datetime.now()}\n\n{e}\n\n{traceback.format_exc()}'
            ping_test(os.getenv('HEALTHCHECK_SNUPHYA') + "/fail", error_message)
