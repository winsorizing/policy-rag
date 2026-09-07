from __future__ import annotations

import logging
from typing import Any, Callable

from app.rule_engine_loan import LoanEngineSnapshot, compute_loan_from_profile
from app.schemas import LoanCalculationResult, RagActionItem, Source

logger = logging.getLogger(__name__)


def _loan_limiting_factor(loan_out: LoanEngineSnapshot) -> str:
    pairs = [
        (loan_out.max_loan_by_ltv, "LTV(주택가격 대비 한도)"),
        (loan_out.max_loan_by_dti, "DTI(소득 대비 원리금 상환 한도)"),
        (loan_out.max_loan_by_dsr, "DSR(소득 대비 총부채 원리금 상환 한도)"),
    ]
    m = loan_out.max_loan_amount
    labels = [lab for amt, lab in pairs if amt == m]
    if not labels:
        return "간이 산출 한도"
    return ", ".join(labels) if len(labels) > 1 else labels[0]


def _rag_action_items(raw: Any) -> list[RagActionItem]:
    out: list[RagActionItem] = []
    if not isinstance(raw, list):
        return out
    for x in raw:
        if not isinstance(x, dict):
            continue
        out.append(
            RagActionItem(
                title=str(x.get("title", "")),
                difficulty=str(x.get("difficulty", "보통")),
                effect=str(x.get("effect", "")),
                full_text=str(x.get("full_text", "")),
            )
        )
    return out


class LoanOrchestrator:
    """
    rule_engine.LoanCalculator(JSON 규칙) 결정론 계산과 RAG(설명)를 분리한 오케스트레이터.
    - calculate_engine_only: 순수 계산
    - explain_policy_with_rag_only: 동일 프로필로 RAG 설명·출처·액션 아이템
    """

    def __init__(
        self,
        rag_ask: Callable[[str | dict[str, Any]], dict[str, Any]],
        normalize_sources: Callable[[list[dict[str, Any]]], list[Source]],
    ) -> None:
        self.rag_ask = rag_ask
        self.normalize_sources = normalize_sources

    @staticmethod
    def _build_result(loan_out: LoanEngineSnapshot, explanation: str) -> LoanCalculationResult:
        return LoanCalculationResult(
            max_loan_amount=int(loan_out.max_loan_amount),
            max_loan_by_ltv=int(loan_out.max_loan_by_ltv),
            max_loan_by_dti=int(loan_out.max_loan_by_dti),
            max_loan_by_dsr=int(loan_out.max_loan_by_dsr),
            ltv_limit=float(loan_out.ltv_limit),
            dti_limit=float(loan_out.dti_limit),
            dsr_limit=float(loan_out.dsr_limit),
            ltv_ratio=float(loan_out.actual_ltv),
            dti_ratio=float(loan_out.actual_dti),
            dsr_ratio=float(loan_out.actual_dsr),
            regulation_type=str(loan_out.regulation_type),
            restrictions=[str(x) for x in loan_out.restrictions],
            limiting_factor=_loan_limiting_factor(loan_out),
            explanation=str(explanation or ""),
        )

    def calculate_engine_only(self, profile: Any) -> LoanCalculationResult:
        loan_out = compute_loan_from_profile(profile)
        return self._build_result(
            loan_out=loan_out,
            explanation="규정에 따른 대출 한도 요약이에요.",
        )

    @staticmethod
    def _loan_rag_payload(
        profile: Any, loan_out: LoanEngineSnapshot, base: LoanCalculationResult
    ) -> dict[str, Any]:
        """``rag_chain.ask_loan_explanation`` 에 넘길 계산·입력 스냅샷."""
        return {
            "max_loan_amount": int(loan_out.max_loan_amount),
            "limiting_factor": base.limiting_factor,
            "regulation_type": str(loan_out.regulation_type),
            "ltv": {
                "actual": float(loan_out.actual_ltv),
                "limit": float(loan_out.ltv_limit),
            },
            "dti": {
                "actual": float(loan_out.actual_dti),
                "limit": float(loan_out.dti_limit),
            },
            "dsr": {
                "actual": float(loan_out.actual_dsr),
                "limit": float(loan_out.dsr_limit),
            },
            "input": {
                "region": str(getattr(profile, "region", "") or ""),
                "house_price": int(getattr(profile, "house_price", 0) or 0),
                "annual_income": int(getattr(profile, "annual_income", 0) or 0),
                "house_count": int(getattr(profile, "house_count", 0) or 0),
                "is_first_home": bool(getattr(profile, "first_time_buyer", False)),
            },
        }

    def explain_policy_with_rag_only(self, profile: Any) -> tuple[str, list[Source], list[RagActionItem]]:
        """동일 프로필로 엔진을 다시 돌린 뒤 RAG만 수행해 (설명, 출처, 액션 아이템) 반환."""
        loan_out = compute_loan_from_profile(profile)
        base = self._build_result(loan_out=loan_out, explanation="")
        payload = self._loan_rag_payload(profile, loan_out, base)
        try:
            rag_raw = self.rag_ask(payload)
        except Exception as e:
            logger.warning("RAG ask 실패 (explain_policy_only): %s", e, exc_info=True)
            msg = (
                "정책 근거 설명(RAG) 생성 중 오류가 발생했습니다.\n"
                f"({type(e).__name__}: {e})"
            )
            return msg, [], []
        answer = str(rag_raw.get("answer", "")).strip()
        try:
            sources = self.normalize_sources(rag_raw.get("sources") or [])
        except Exception as e:
            logger.warning("RAG 출처 정규화 실패: %s", e, exc_info=True)
            sources = []
        actions = _rag_action_items(rag_raw.get("action_items"))
        return (
            answer or "관련 정책 설명을 생성하지 못했습니다.",
            sources,
            actions,
        )

