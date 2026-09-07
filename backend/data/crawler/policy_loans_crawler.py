from __future__ import annotations

import copy
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

_DATA_DIR = Path(__file__).resolve().parent.parent

DEFAULT_BASELINE_JSON = _DATA_DIR / "rules" / "manual" / "policy_loans.json"
DEFAULT_OUTPUT_JSON = _DATA_DIR / "rules" / "crawled" / "policy_loans.json"

MOLIT_BASE_URL = "https://www.molit.go.kr"
MOLIT_POLICY_PATHS = [
    "/policy/main.jsp",
    "/policy/stable/sta_b_03.jsp",
    "/policy/stable/sta_b_02.jsp",
    "/policy/stable/sta_a_01.jsp",
    "/policy/stable/sta_b_01.jsp",
]
HF_BASE_URL = "https://www.hf.go.kr"
HUG_BASE_URL = "https://www.khug.or.kr"


def _norm_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip()


class PolicyLoansCrawler:
    """정책대출(디딤돌 등) 관련 숫자 힌트를 수집해 policy_loans.json 스키마로 저장."""

    def __init__(self) -> None:
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.molit.go.kr",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._sources: List[str] = []
        self._text_chunks: List[str] = []

    def _fetch_html(self, url: str, *, timeout: int = 15) -> str | None:
        try:
            r = self.session.get(url, timeout=timeout)
            r.raise_for_status()
            if r.encoding is None or r.encoding.lower() in ("iso-8859-1", "ascii"):
                r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            print(f"   ⚠️ 요청 실패 {url}: {e}")
            return None

    @staticmethod
    def _soup_text(soup: BeautifulSoup) -> str:
        return _norm_whitespace(soup.get_text(separator=" ", strip=False))

    def _crawl_from_molit(self) -> None:
        print("\n📄 국토부 정책 페이지 (정책대출 문맥 수집)...")
        for path in MOLIT_POLICY_PATHS:
            url = f"{MOLIT_BASE_URL}{path}"
            html = self._fetch_html(url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            text = self._soup_text(soup)
            self._text_chunks.append(text)
            self._sources.append(url)
            print(f"   · {path} (본문 {len(text)}자)")
            time.sleep(0.35)

    def _crawl_from_public_sites(self) -> None:
        """
        공개 사이트 메인/검색 페이지에서 단문 힌트만 수집.
        실패해도 baseline 기반 산출은 유지.
        """
        print("\n🌐 공공기관 페이지 보조 수집...")
        candidates = [
            f"{HF_BASE_URL}/",
            f"{HUG_BASE_URL}/",
            f"{MOLIT_BASE_URL}/search/search.jsp?query=디딤돌대출",
        ]
        for url in candidates:
            html = self._fetch_html(url, timeout=12)
            if not html:
                continue
            text = self._soup_text(BeautifulSoup(html, "html.parser"))
            if text:
                self._text_chunks.append(text)
                self._sources.append(url)
            time.sleep(0.35)

    @staticmethod
    def _load_baseline_json(path: Path) -> Dict[str, Any]:
        if path.is_file():
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        raise FileNotFoundError(f"baseline JSON 없음 또는 형식 오류: {path}")

    @staticmethod
    def _extract_policy_candidates(text: str) -> Dict[str, Any]:
        """
        디딤돌대출 중심으로 보수적 추출.
        파싱 실패 시 빈 dict 반환(= baseline 유지).
        """
        out: Dict[str, Any] = {}

        # 소득 한도 (원문에 '연소득 ... 이하')
        income_hits = []
        for m in re.finditer(r"연소득\s*([0-9][0-9,]*)\s*만원\s*(?:이하|미만)", text):
            v = int(m.group(1).replace(",", "")) * 10_000
            if 10_000_000 <= v <= 300_000_000:
                income_hits.append(v)
        if income_hits:
            out["income_limit"] = max(income_hits)

        # 주택가격 한도
        house_hits = []
        for m in re.finditer(r"(?:주택가격|주택가액)\s*([0-9][0-9,]*)\s*만원\s*(?:이하|미만)", text):
            v = int(m.group(1).replace(",", "")) * 10_000
            if 100_000_000 <= v <= 2_000_000_000:
                house_hits.append(v)
        if house_hits:
            out["house_price_limit"] = max(house_hits)

        # 최대 대출한도
        max_hits = []
        for m in re.finditer(r"(?:최대|한도)\s*([0-9][0-9,]*)\s*만원", text):
            v = int(m.group(1).replace(",", "")) * 10_000
            if 50_000_000 <= v <= 1_000_000_000:
                max_hits.append(v)
        if max_hits:
            out["max_amount"] = max(max_hits)

        # LTV / DTI
        ltv_m = re.search(r"LTV\s*[∶:]?\s*(\d{1,2})\s*%", text, re.I)
        if ltv_m:
            out["ltv"] = int(ltv_m.group(1))
        dti_m = re.search(r"DTI\s*[∶:]?\s*(\d{1,2})\s*%", text, re.I)
        if dti_m:
            out["dti"] = int(dti_m.group(1))

        return out

    @staticmethod
    def _safe_apply_numeric(item: Dict[str, Any], key: str, value: Any) -> None:
        if key not in item:
            return
        old = item.get(key)
        if isinstance(old, bool):
            return
        if isinstance(old, (int, float)) and isinstance(value, (int, float)):
            item[key] = value

    @classmethod
    def _apply_candidates(cls, base: Dict[str, Any], cands: Dict[str, Any]) -> None:
        products = base.get("products")
        if not isinstance(products, dict):
            return
        dd = products.get("디딤돌대출")
        if not isinstance(dd, dict):
            return

        # 수치 필드만 선택 반영
        for section in ("general", "first_home", "newlywed"):
            target = dd.get(section)
            if not isinstance(target, dict):
                continue
            for key in ("income_limit", "house_price_limit", "max_amount", "ltv", "dti"):
                if key in cands:
                    cls._safe_apply_numeric(target, key, cands[key])

    def crawl_policy_loans(self) -> Dict[str, Any]:
        print("🔍 정책대출 규칙 크롤링 시작...")
        self._sources = []
        self._text_chunks = []

        self._crawl_from_molit()
        self._crawl_from_public_sites()

        combined = _norm_whitespace(" ".join(self._text_chunks))
        print(f"\n📎 수집 본문 합계: {len(combined)}자")

        cands = self._extract_policy_candidates(combined)
        print(f"   추출 정책대출 후보: {cands or '(없음)'}")

        baseline_path = Path(
            os.environ.get("POLICY_LOANS_BASELINE_JSON", str(DEFAULT_BASELINE_JSON))
        )
        out = copy.deepcopy(self._load_baseline_json(baseline_path))
        out["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        prev = str(out.get("source", ""))
        out["source"] = f"{prev}; 웹크롤 병합 ({datetime.now().date()})".strip("; ")

        if cands:
            self._apply_candidates(out, cands)

        out["crawl_meta"] = {
            "generated_at": datetime.now().isoformat(),
            "baseline": str(baseline_path.resolve()),
            "sources": self._sources[:25],
            "extracted_policy_candidates": cands,
        }
        print("\n✅ 정책대출 크롤·병합 완료")
        return out

    def save_to_json(
        self,
        output_file: str | Path | None = None,
        *,
        run_crawl: bool = True,
        baseline_json: str | Path | None = None,
    ) -> str:
        out_path = Path(output_file) if output_file else DEFAULT_OUTPUT_JSON
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if baseline_json:
            os.environ["POLICY_LOANS_BASELINE_JSON"] = str(Path(baseline_json).resolve())

        if run_crawl:
            result = self.crawl_policy_loans()
        else:
            baseline_path = Path(
                os.environ.get("POLICY_LOANS_BASELINE_JSON", str(DEFAULT_BASELINE_JSON))
            )
            result = self._load_baseline_json(baseline_path)

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n💾 {out_path.resolve()} 저장 완료")
        return str(out_path.resolve())


def run() -> None:
    crawler = PolicyLoansCrawler()
    crawler.save_to_json()


if __name__ == "__main__":
    run()
