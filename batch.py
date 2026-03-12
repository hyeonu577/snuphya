import datetime
import json
import logging
import os

import jsonlines

from config import JSONL_FOLDER, get_openai_client

logger = logging.getLogger('snuphya')

SUMMARY_SYSTEM_PROMPT = '''당신은 공지사항을 요약하는 전문가입니다. 공지사항 본문을 분석하여 3문장 이하로 요약하세요. 각 문장은 번호를 매기세요. 모든 응답은 한국어로 작성하세요. 단, 전문 용어는 다른 언어를 사용해도 됩니다.

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


def generate_each_line_of_batch_file(announcement):
    message = f'제목: {announcement["title"]}\n본문: {announcement["body"]}'
    if 'image_code' in announcement:
        final_user_message = [{"type": "text", "text": message}]
        for each_image_code in announcement['image_code']:
            final_user_message.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{each_image_code}"}})
    else:
        final_user_message = message
    return {
        "custom_id": announcement['hash'],
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": final_user_message}
            ],
            "max_tokens": 500,
            "temperature": 0.3,
            "model": "gpt-4.1-nano"
        }
    }


def generate_batch_file(announcement_list):
    jsonl_data = [generate_each_line_of_batch_file(a) for a in announcement_list]
    jsonl_file_name = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    jsonl_file_path = f"{JSONL_FOLDER}/{jsonl_file_name}.jsonl"
    with jsonlines.open(jsonl_file_path, mode="w") as writer:
        writer.write_all(jsonl_data)
    logger.info(f'generated batch file: {jsonl_file_path}')
    return jsonl_file_path


def upload_batch_file(batch_file_path):
    client = get_openai_client()
    with open(batch_file_path, "rb") as f:
        batch_input_file = client.files.create(file=f, purpose="batch")
    os.remove(batch_file_path)
    return batch_input_file


def start_processing_batch_file(batch_file_path):
    batch_input_file = upload_batch_file(batch_file_path)
    client = get_openai_client()
    return client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h"
    )


def get_batch_result(batch_id):
    client = get_openai_client()
    batch = client.batches.retrieve(batch_id)
    if batch.status == 'completed':
        if batch.request_counts.completed == 0:
            raise Exception('failed')
        file_response = client.files.content(batch.output_file_id)
        good_result = file_response.text
        if batch.request_counts.failed == 0:
            return good_result
        error_response = client.files.content(batch.error_file_id)
        return good_result + error_response.text
    elif batch.status in ['validating', 'in_progress', 'finalizing']:
        raise Exception('in progress')
    elif batch.status in ['failed', 'expired', 'cancelling', 'cancelled']:
        raise Exception('failed')
    else:
        raise Exception('unexpected error')


def convert_batch_result_into_readable_form(batch_result):
    results = []
    for line in batch_result.splitlines():
        entry = json.loads(line)
        if entry['response']['status_code'] == 200:
            answer = entry["response"]["body"]["choices"][0]["message"]["content"]
        else:
            answer = '요약 중 오류 발생'
        results.append((entry['custom_id'], answer))
    return results
