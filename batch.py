import base64
import logging

from config import HAIKU_MODEL, get_anthropic_client

logger = logging.getLogger('snuphya')

# Haiku 5.5 thinks by default, and thinking counts toward max_tokens
SUMMARY_MAX_TOKENS = 8000
# Claude rejects images over 5 MB; drop them so the text still gets summarized
MAX_IMAGE_BASE64_LENGTH = 5 * 1024 * 1024

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


_IMAGE_SIGNATURES = [
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'GIF87a', 'image/gif'),
    (b'GIF89a', 'image/gif'),
]


def detect_image_media_type(image_code):
    head = base64.b64decode(image_code[:16])
    for signature, media_type in _IMAGE_SIGNATURES:
        if head.startswith(signature):
            return media_type
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    return None


def make_image_block(image_code):
    if not image_code:  # download_image returns False on failure
        return None
    if len(image_code) > MAX_IMAGE_BASE64_LENGTH:
        logger.warning('image over 5 MB, skipping it in the summary request')
        return None
    media_type = detect_image_media_type(image_code)
    if media_type is None:
        logger.warning('unsupported image format, skipping it in the summary request')
        return None
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_code}}


def generate_batch_request(announcement):
    message = f'제목: {announcement["title"]}\n본문: {announcement["body"]}'
    image_blocks = [block for block in map(make_image_block, announcement.get('image_code', [])) if block]
    if image_blocks:
        final_user_message = [{"type": "text", "text": message}] + image_blocks
    else:
        final_user_message = message
    return {
        "custom_id": announcement['hash'],
        "params": {
            "model": HAIKU_MODEL,
            "max_tokens": SUMMARY_MAX_TOKENS,
            "system": SUMMARY_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": final_user_message}],
            "output_config": {"effort": "medium"},
        }
    }


def generate_batch_requests(announcement_list):
    return [generate_batch_request(a) for a in announcement_list]


def start_processing_batch(requests):
    batch = get_anthropic_client().messages.batches.create(requests=requests)
    logger.info(f'created batch {batch.id} with {len(requests)} request(s)')
    return batch


def extract_summary_text(message):
    # only a cleanly finished response counts; max_tokens or refusal yields None
    if message.stop_reason != 'end_turn':
        return None
    text = ''.join(block.text for block in message.content if block.type == 'text')
    return text if text.strip() else None


def describe_failure(result):
    if result.type == 'succeeded':
        return f'stop_reason={result.message.stop_reason}'
    if result.type == 'errored':
        return str(result.error)[:300]
    return result.type  # canceled or expired


def get_batch_result(batch_id):
    if not batch_id.startswith('msgbatch_'):
        # OpenAI batch left over from before the switch to Claude
        raise Exception('failed')
    # keep the client referenced until the results stream is fully read
    client = get_anthropic_client()
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status in ['in_progress', 'canceling']:
        raise Exception('in progress')
    if batch.processing_status != 'ended':
        raise Exception('unexpected error')
    # results_url is gone once the 29-day retention passes
    results = list(client.messages.batches.results(batch_id)) if batch.results_url else []
    if batch.request_counts.succeeded == 0 or not results:
        for each in results:
            logger.error(f'{each.custom_id} 요약 실패 원인: {describe_failure(each.result)}')
        raise Exception('failed')
    return results


def convert_batch_result_into_readable_form(batch_result):
    results = []
    for each in batch_result:
        summary = None
        if each.result.type == 'succeeded':
            summary = extract_summary_text(each.result.message)
        if summary is None:
            logger.error(f'{each.custom_id} 요약 오류: {describe_failure(each.result)}')
            summary = '요약 중 오류 발생'
        results.append((each.custom_id, summary))
    return results
