import logging
import os
import smtplib

from todoist_api_python.api import TodoistAPI
from true_email import true_email
from true_line import true_line

from config import get_openai_client
from models import AnnouncementCheck

logger = logging.getLogger('snuphya')


def send_announcement_email(subject, body, announcement):
    image_code = None
    if 'image_code' in announcement and announcement['image_code']:
        image_code = announcement['image_code'][0]
    files = announcement.get('file', [])
    try:
        true_email.self_email(subject, body, image_code, files)
    except smtplib.SMTPSenderRefused:
        true_email.self_email(subject, f'{body}\n첨부파일 건너뜀')


def make_email_subject(announcement, include_header=True):
    link = announcement['link']
    title = announcement['title']
    if 'id=undergraduate' in link:
        return f'{"[물천인트라넷]" if include_header else ""}[학부] {title}'
    elif 'id=graduate' in link:
        return f'{"[물천인트라넷] " if include_header else ""}{title}'
    else:
        return f'{"[물천인트라넷]" if include_header else ""}[?] {title}'


def related_to_grad_school(announcement):
    link = announcement['link']
    if 'id=graduate' in link:
        return True
    body = f'{announcement["title"]}\n{announcement["body"]}'
    return any(keyword in body for keyword in ['대학원', '대학(원)', '석사', '박사', '석박'])


def format_announcement_body(announcement, summary=None):
    if summary:
        body = f'{summary}\n\n{announcement["body"]}\n\n'
    else:
        body = f'요약 전체 실패\n\n\n{announcement["body"]}\n\n'
    body += (f'확인 시간: {announcement["check_time"]}\n'
             f'조회수: {announcement["view_count"]}\n')
    for each_file in announcement.get('file', []):
        body += f'{each_file["code"]}: {each_file["name"]}\n'
    return body


def analyze_announcement_if_urgent(announcement_subject, announcement_content):
    client = get_openai_client()
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
    completion = client.beta.chat.completions.parse(
        model="gpt-5-mini-2025-08-07",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_input},
        ],
        response_format=AnnouncementCheck,
    )
    result = completion.choices[0].message.parsed
    logger.info(f'{announcement_subject}\n분석 결과: {result}')
    return result


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
    logger.info(f"작업 생성 성공: {task.content} (ID: {task.id})")


def finalize_processing_batch(new_left_batch, get_batch_announcements):
    announcement_list = []
    for each_batch in new_left_batch:
        announcement_list.extend(get_batch_announcements(each_batch))
    subject = '[물천인트라넷] 요약 진행중'
    body = ''
    for a in announcement_list:
        body += (f'{a["title"]}\n\n'
                 f'조회수: {a["view_count"]}\n'
                 f'확인 시간: {a["check_time"]}\n'
                 f'링크: {a["link"]}\n\n\n')
    body += f'\n{"-" * 10}\n'
    for a in announcement_list:
        body += (f'제목: {a["title"]}\n\n'
                 f'본문:\n{a["body"]}\n\n\n')
    body = body.strip()
    true_email.self_email(subject, body)


def check_if_urgent(announcement_list):
    if not announcement_list:
        logger.info('no to-be-checked announcement')
        return
    for announcement in announcement_list:
        if not related_to_grad_school(announcement):
            continue
        analysis_result = analyze_announcement_if_urgent(
            announcement['title'], announcement['body'])
        if not analysis_result.has_compensation:
            continue

        subject = '[물천인트라넷][중요] ' + announcement['title']
        body = (f'{announcement["body"]}\n\n\n'
                f'인원 제한: {analysis_result.has_participant_limit}\n\n'
                f'판단 근거: {analysis_result.reasoning}\n\n'
                f'확인 시간: {announcement["check_time"]}\n'
                f'조회수: {announcement["view_count"]}\n'
                f'링크: {announcement["link"]}\n')
        for each_file in announcement.get('file', []):
            body += f'{each_file["code"]}: {each_file["name"]}\n'

        send_announcement_email(subject, body, announcement)

        if analysis_result.has_participant_limit:
            line_body = (f'{subject}\n\n인원 제한: {analysis_result.has_participant_limit}\n'
                         f'판단 근거: {analysis_result.reasoning}')
            true_line.send_text(line_body)
            add_todolist(
                announcement['title'],
                f'인원 제한: {analysis_result.has_participant_limit}\n판단 근거: {analysis_result.reasoning}',
                due_date='in 5 minutes', priority=4)
        else:
            add_todolist(
                announcement['title'],
                f'인원 제한: {analysis_result.has_participant_limit}\n판단 근거: {analysis_result.reasoning}',
                due_date='today', priority=2)

        yield announcement
