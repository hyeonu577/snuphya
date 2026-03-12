from pydantic import BaseModel, Field


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
