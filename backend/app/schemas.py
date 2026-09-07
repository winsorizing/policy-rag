from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """프론트엔드 `UserProfile` 타입과 동일."""

    first_time_buyer: bool = Field(description="생애최초 주택구입 여부")
    married: bool = Field(description="혼인 여부")
    house_count: int = Field(default=1, ge=0, description="보유 주택 수")
    annual_income: float = Field(ge=0, description="연소득(원)")
    region: str = Field(description="대상 주택 지역")
    house_price: float = Field(ge=0, description="주택 가격(원)")
    product_cap_amount: float = Field(default=0, ge=0, description="상품별 최대 한도(원, 없으면 0)")


class ProfileInsightRequest(UserProfile):
    """프로필 + 요약 엔진 선택(local Ollama / OpenAI / 양쪽 비교)."""

    insight_mode: Literal["local", "openai", "compare"] = Field(
        default="local",
        description="local: Ollama RAG, openai: OpenAI 챗 + 동일 Chroma 검색, compare: 둘 다",
    )


class QueryRequest(BaseModel):
    question: str
    user_profile: Optional[UserProfile] = None
    llm_mode: Literal["local", "openai"] = Field(
        default="local",
        description="local: Ollama, openai: ChatOpenAI + 동일 벡터 검색",
    )


class SourceMetadata(BaseModel):
    title: str
    source: str
    date: str
    category: str
    chunk_index: int


class Source(BaseModel):
    content: str
    metadata: SourceMetadata


class PolicyResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list)
    mode: Optional[Literal["local", "openai", "compare"]] = None
    local_answer: Optional[str] = None
    openai_answer: Optional[str] = None
    llm_model: Optional[str] = Field(
        default=None,
        description="단일 모드(local/openai)일 때 사용된 챗 모델 라벨",
    )
    local_llm_model: Optional[str] = Field(
        default=None,
        description="비교 모드일 때 Local(Ollama) 쪽 라벨",
    )
    openai_llm_model: Optional[str] = Field(
        default=None,
        description="비교 모드일 때 OpenAI 쪽 라벨",
    )


class LoanCalculationResult(BaseModel):
    max_loan_amount: int
    max_loan_by_ltv: int
    max_loan_by_dti: int
    max_loan_by_dsr: int
    ltv_limit: float
    dti_limit: float
    dsr_limit: float
    ltv_ratio: float
    dti_ratio: float
    dsr_ratio: float
    regulation_type: str
    restrictions: list[str]
    limiting_factor: str
    explanation: str


class RagActionItem(BaseModel):
    """RAG 대출 설명에서 추출한 실행 팁 블록."""

    title: str = ""
    difficulty: str = "보통"
    effect: str = ""
    full_text: str = ""


class PolicyExplainResponse(BaseModel):
    """Rule 엔진과 분리된 정책 문서 기반 설명만 (RAG)."""

    explanation: str
    sources: list[Source] = Field(default_factory=list)
    action_items: list[RagActionItem] = Field(default_factory=list)
    llm_model: str | None = Field(
        default=None,
        description="정책 설명에 사용된 Ollama 모델 태그(예: gemma4:latest)",
    )
