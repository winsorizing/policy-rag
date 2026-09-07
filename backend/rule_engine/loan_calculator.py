# rule_engine/loan_calculator.py

from typing import Dict, Tuple
from datetime import datetime
from .data_loader import RuleDataLoader


class LoanCalculator:
    """JSON 기반 대출 계산 엔진"""

    MONTHS_PER_YEAR = 12
    DEFAULT_LOAN_PERIOD = 30

    def __init__(self, rules_dir: str = "data/rules"):
        self.loader = RuleDataLoader(rules_dir)

        # 데이터 로드
        self.regulation_areas = self.loader.get_regulation_areas()
        self.ltv_rules = self.loader.get_ltv_rules()
        self.dti_dsr_rules = self.loader.get_dti_dsr_rules()
        self.policy_loans = self.loader.get_policy_loans()

    # ========================================
    # 1단계: 규제지역 확인
    # ========================================
    def identify_regulation_type(self, region: str) -> str:
        """지역 → 규제 유형 판단"""

        regions = self.regulation_areas["regions"]

        # 투기과열지구 확인
        if region in regions["투기과열지구"]:
            return "투기과열지구"

        # 조정대상지역 확인
        for area in regions["조정대상지역"]:
            if area in region or region in area:
                return "조정대상지역"

        return "일반지역"

    # ========================================
    # 2단계: LTV 계산
    # ========================================
    def get_ltv_limit(
        self,
        regulation_type: str,
        house_price: int,
        house_count: int,
        is_first_home: bool,
    ) -> Tuple[float, str]:
        """LTV 한도 조회"""

        rules = self.ltv_rules["rules"][regulation_type]
        price_threshold = rules["price_threshold"]

        # 가격 구간 선택
        if house_price <= price_threshold:
            price_rules = rules["below_threshold"]
        else:
            price_rules = rules["above_threshold"]

        # 주택 보유 상태별 LTV 결정
        if regulation_type == "투기과열지구":
            if house_price <= price_threshold:
                if house_count == 0 and is_first_home:
                    rule = price_rules["무주택_생애최초"]
                elif house_count == 0:
                    rule = price_rules["무주택"]
                elif house_count == 1:
                    rule = price_rules["1주택"]
                elif house_count == 2:
                    rule = price_rules["2주택"]
                else:
                    rule = price_rules["3주택_이상"]
            else:
                if house_count == 0 and is_first_home:
                    rule = price_rules["무주택_생애최초"]
                else:
                    rule = price_rules["일반"]

        elif regulation_type == "조정대상지역":
            if house_price <= price_threshold:
                if house_count == 0 and is_first_home:
                    rule = price_rules["무주택_생애최초"]
                elif house_count == 0:
                    rule = price_rules["무주택"]
                elif house_count == 1:
                    rule = price_rules["1주택"]
                elif house_count == 2:
                    rule = price_rules["2주택"]
                else:
                    rule = price_rules["3주택_이상"]
            else:
                if house_count == 0:
                    rule = price_rules["무주택"]
                elif house_count == 1:
                    rule = price_rules["1주택"]
                elif house_count == 2:
                    rule = price_rules["2주택"]
                else:
                    rule = price_rules["3주택_이상"]

        else:  # 일반지역
            if house_price <= price_threshold:
                if is_first_home:
                    rule = price_rules["생애최초"]
                else:
                    rule = price_rules["일반"]
            else:
                rule = price_rules["일반"]

        return rule["ltv"], rule["condition"]

    def calculate_max_loan_by_ltv(self, house_price: int, ltv_limit: float) -> int:
        """LTV 기준 최대 대출액"""

        return int(house_price * (ltv_limit / 100))

    # ========================================
    # 3단계: DTI 계산
    # ========================================
    def get_dti_limit(self, regulation_type: str, house_count: int) -> float:
        """DTI 한도 조회"""

        dti_rules = self.dti_dsr_rules["dti_rules"]

        if regulation_type in ["투기과열지구", "조정대상지역"]:
            rules = dti_rules[regulation_type]

            if house_count == 0:
                key = "0주택"
            elif house_count == 1:
                key = "1주택"
            elif house_count == 2:
                key = "2주택"
            else:
                key = "3주택_이상"

            return rules[key]

        else:  # 일반지역
            return dti_rules["일반지역"]["전체"]

    def calculate_max_loan_by_dti(
        self,
        annual_income: int,
        dti_limit: float,
        loan_period_years: int = 30,
    ) -> int:
        """DTI 기준 최대 대출액 (원금을 만기까지 균등 분할한다고 가정, 금리 미사용)."""

        if dti_limit == 0:
            return 0

        max_annual_payment = annual_income * (dti_limit / 100)
        max_monthly_payment = max_annual_payment / self.MONTHS_PER_YEAR
        total_months = loan_period_years * self.MONTHS_PER_YEAR

        return int(max_monthly_payment * total_months)

    # ========================================
    # 4단계: DSR 계산
    # ========================================
    def get_dsr_limit(self, annual_income: int) -> float:
        """DSR 한도 조회"""

        dsr_rules = self.dti_dsr_rules["dsr_rules"]

        if annual_income >= 150000000:
            return dsr_rules["고소득자"]["limit"]
        else:
            return dsr_rules["기본"]["limit"]

    def calculate_max_loan_by_dsr(
        self,
        annual_income: int,
        existing_debt_monthly_payment: int,
        loan_period_years: int = 30,
    ) -> int:
        """DSR 기준 최대 대출액 (원금 균등 분할 가정, 금리 미사용)."""

        dsr_limit = self.get_dsr_limit(annual_income)

        max_total_annual_payment = annual_income * (dsr_limit / 100)
        existing_annual_payment = existing_debt_monthly_payment * self.MONTHS_PER_YEAR
        available_annual_payment = max_total_annual_payment - existing_annual_payment

        if available_annual_payment <= 0:
            return 0

        available_monthly_payment = available_annual_payment / self.MONTHS_PER_YEAR
        total_months = loan_period_years * self.MONTHS_PER_YEAR

        return int(available_monthly_payment * total_months)

    # ========================================
    # 5단계: 정책대출 확인
    # ========================================
    def check_policy_loan_eligibility(
        self,
        annual_income: int,
        house_price: int,
        house_count: int,
        is_first_home: bool,
        is_married: bool,
        marriage_years: int = 0,
    ) -> Dict:
        """정책대출 가능 여부 확인"""

        eligible_products = []

        diditdol = self.policy_loans["products"]["디딤돌대출"]

        # 기본 조건 확인
        if house_count > 0:
            return {"eligible": False, "products": []}

        # 생애최초 디딤돌
        if is_first_home:
            first_home = diditdol["first_home"]
            if annual_income <= first_home["income_limit"] and house_price <= first_home["house_price_limit"]:
                eligible_products.append(
                    {
                        "name": "디딤돌대출 (생애최초)",
                        "max_amount": first_home["max_amount"],
                        "ltv": first_home["ltv"],
                    }
                )

        # 신혼부부 디딤돌
        if is_married and marriage_years <= diditdol["newlywed"]["marriage_period"]:
            newlywed = diditdol["newlywed"]
            if annual_income <= newlywed["income_limit"] and house_price <= newlywed["house_price_limit"]:
                eligible_products.append(
                    {
                        "name": "디딤돌대출 (신혼부부)",
                        "max_amount": newlywed["max_amount"],
                        "ltv": newlywed["ltv"],
                    }
                )

        # 일반 디딤돌
        general = diditdol["general"]
        if annual_income <= general["income_limit"] and house_price <= general["house_price_limit"]:
            eligible_products.append(
                {
                    "name": "디딤돌대출 (일반)",
                    "max_amount": general["max_amount"],
                    "ltv": general["ltv"],
                }
            )

        return {"eligible": len(eligible_products) > 0, "products": eligible_products}

    def _monthly_principal_payment(self, loan_amount: int, loan_period_years: int = 30) -> int:
        """원금 균등 월 상환액(이자 없음)."""
        if loan_amount == 0:
            return 0
        total_months = max(1, loan_period_years * self.MONTHS_PER_YEAR)
        return int(loan_amount / total_months)

    # ========================================
    # 종합 계산
    # ========================================
    def calculate(
        self,
        annual_income: int,
        house_count: int,
        is_married: bool,
        region: str,
        house_price: int,
        is_first_home: bool = False,
        marriage_years: int = 0,
        existing_debt_monthly_payment: int = 0,
        loan_period_years: int | None = None,
        product_cap_amount: int = 0,
    ) -> Dict:
        """
        종합 대출 계산 (금리·신용점수 미사용).
        DTI/DSR 역산은 원금을 만기까지 균등 상환한다고 가정한다.
        """
        years = loan_period_years if loan_period_years is not None else self.DEFAULT_LOAN_PERIOD

        regulation_type = self.identify_regulation_type(region)

        ltv_limit, ltv_reason = self.get_ltv_limit(regulation_type, house_price, house_count, is_first_home)
        max_loan_by_ltv = self.calculate_max_loan_by_ltv(house_price, ltv_limit)

        dti_limit = self.get_dti_limit(regulation_type, house_count)
        max_loan_by_dti = self.calculate_max_loan_by_dti(annual_income, dti_limit, years)

        max_loan_by_dsr = self.calculate_max_loan_by_dsr(
            annual_income, existing_debt_monthly_payment, years
        )

        policy_loan_info = self.check_policy_loan_eligibility(
            annual_income, house_price, house_count, is_first_home, is_married, marriage_years
        )

        pre_cap_min = min(max_loan_by_ltv, max_loan_by_dti, max_loan_by_dsr)
        max_loan_amount = pre_cap_min
        cap = max(0, int(product_cap_amount or 0))
        if cap > 0:
            max_loan_amount = min(max_loan_amount, cap)

        if cap > 0 and max_loan_amount < pre_cap_min:
            limiting_factor = "상품한도"
        elif max_loan_amount == max_loan_by_ltv:
            limiting_factor = "LTV"
        elif max_loan_amount == max_loan_by_dti:
            limiting_factor = "DTI"
        else:
            limiting_factor = "DSR"

        monthly_payment = self._monthly_principal_payment(max_loan_amount, years)

        actual_ltv = (max_loan_amount / house_price * 100) if house_price > 0 else 0

        annual_payment = monthly_payment * 12
        actual_dti = (annual_payment / annual_income * 100) if annual_income > 0 else 0

        total_debt_payment = annual_payment + (existing_debt_monthly_payment * 12)
        actual_dsr = (total_debt_payment / annual_income * 100) if annual_income > 0 else 0

        return {
            "max_loan_amount": max_loan_amount,
            "monthly_payment": monthly_payment,
            "regulation_type": regulation_type,
            "limiting_factor": limiting_factor,
            "ltv": {
                "limit": ltv_limit,
                "actual": round(actual_ltv, 2),
                "max_loan": max_loan_by_ltv,
                "reason": ltv_reason,
            },
            "dti": {
                "limit": dti_limit,
                "actual": round(actual_dti, 2),
                "max_loan": max_loan_by_dti,
            },
            "dsr": {
                "limit": self.get_dsr_limit(annual_income),
                "actual": round(actual_dsr, 2),
                "max_loan": max_loan_by_dsr,
            },
            "policy_loans": policy_loan_info,
            "input": {
                "annual_income": annual_income,
                "house_count": house_count,
                "is_married": is_married,
                "region": region,
                "house_price": house_price,
                "is_first_home": is_first_home,
                "loan_period_years": years,
            },
            "calculated_at": datetime.now().isoformat(),
        }
