"""UserProfile → rule_engine.LoanCalculator 입력 매핑 및 결과를 API 스키마용 스냅샷으로 변환."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rule_engine.loan_calculator import LoanCalculator

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_RULES_BASE_DIR = _BACKEND_ROOT / "data" / "rules"
_MERGE_RULES_DIR = _RULES_BASE_DIR / "merge"
_MANUAL_RULES_DIR = _RULES_BASE_DIR / "manual"

_calculator: LoanCalculator | None = None


def reset_loan_calculator() -> None:
    """디스크의 ``rules/merge``(또는 manual) 변경 후 다음 계산에서 다시 로드하도록 캐시 비움."""
    global _calculator
    _calculator = None


def _get_loan_calculator() -> LoanCalculator:
    global _calculator
    if _calculator is None:
        # 크롤+병합 결과를 우선 사용하고, 없으면 manual로 폴백
        rules_dir = _MERGE_RULES_DIR if (_MERGE_RULES_DIR / "regulation_areas.json").is_file() else _MANUAL_RULES_DIR
        _calculator = LoanCalculator(rules_dir=str(rules_dir))
    return _calculator


@dataclass
class LoanEngineSnapshot:
    """loan_orchestrator._build_result / RAG 프롬프트가 기대하는 필드."""

    max_loan_amount: int
    max_loan_by_ltv: int
    max_loan_by_dti: int
    max_loan_by_dsr: int
    ltv_limit: float
    dti_limit: float
    dsr_limit: float
    actual_ltv: float
    actual_dti: float
    actual_dsr: float
    regulation_type: str
    restrictions: list[str]


def profile_to_calculator_kwargs(profile: Any) -> dict[str, Any]:
    """app.schemas.UserProfile 등 동일 속성을 가진 객체를 LoanCalculator.calculate 인자로 변환."""
    annual_income = max(0, int(getattr(profile, "annual_income", 0)))
    house_count = max(0, int(getattr(profile, "house_count", 0)))
    is_married = bool(getattr(profile, "married", False))
    region = str(getattr(profile, "region", "") or "기타 지역").strip() or "기타 지역"
    house_price = max(0, int(getattr(profile, "house_price", 0)))
    is_first_home = bool(getattr(profile, "first_time_buyer", False))
    marriage_years = 3 if is_married else 0
    product_cap = max(0, int(float(getattr(profile, "product_cap_amount", 0) or 0)))

    return {
        "annual_income": annual_income,
        "house_count": house_count,
        "is_married": is_married,
        "region": region,
        "house_price": house_price,
        "is_first_home": is_first_home,
        "marriage_years": marriage_years,
        "existing_debt_monthly_payment": 0,
        "product_cap_amount": product_cap,
    }


def raw_result_to_snapshot(raw: dict[str, Any]) -> LoanEngineSnapshot:
    ltv = raw.get("ltv") or {}
    dti = raw.get("dti") or {}
    dsr = raw.get("dsr") or {}
    policy = raw.get("policy_loans") or {}

    restrictions: list[str] = []
    if policy.get("eligible") and isinstance(policy.get("products"), list):
        names = [str(p.get("name", "")) for p in policy["products"] if p.get("name")]
        if names:
            restrictions.append("정책대출 후보: " + ", ".join(names[:5]))

    return LoanEngineSnapshot(
        max_loan_amount=int(raw.get("max_loan_amount", 0)),
        max_loan_by_ltv=int(ltv.get("max_loan", 0)),
        max_loan_by_dti=int(dti.get("max_loan", 0)),
        max_loan_by_dsr=int(dsr.get("max_loan", 0)),
        ltv_limit=float(ltv.get("limit", 0)),
        dti_limit=float(dti.get("limit", 0)),
        dsr_limit=float(dsr.get("limit", 0)),
        actual_ltv=float(ltv.get("actual", 0)),
        actual_dti=float(dti.get("actual", 0)),
        actual_dsr=float(dsr.get("actual", 0)),
        regulation_type=str(raw.get("regulation_type", "일반지역")),
        restrictions=restrictions,
    )


def compute_loan_from_profile(profile: Any) -> LoanEngineSnapshot:
    calc = _get_loan_calculator()
    kwargs = profile_to_calculator_kwargs(profile)
    raw = calc.calculate(**kwargs)
    return raw_result_to_snapshot(raw)
