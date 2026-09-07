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

DEFAULT_BASELINE_JSON = _DATA_DIR / "rules" / "manual" / "ltv_rules.json"
DEFAULT_OUTPUT_JSON = _DATA_DIR / "rules" / "crawled" / "ltv_rules.json"

MOLIT_BASE_URL = "https://www.molit.go.kr"
MOLIT_POLICY_PATHS = [
    "/policy/main.jsp",
    "/policy/stable/sta_b_03.jsp",
    "/policy/stable/sta_b_02.jsp",
    "/policy/stable/sta_a_01.jsp",
    "/policy/stable/sta_b_01.jsp",
]


def _norm_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip()


class LtvRulesCrawler:
    """국토부 정책 본문에서 LTV 수치 힌트를 추출해 ltv_rules.json 스키마로 저장."""

    def __init__(self) -> None:
        self.base_url = MOLIT_BASE_URL
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

    def _fetch_html(self, path: str) -> str | None:
        url = f"{self.base_url}{path}" if path.startswith("/") else path
        try:
            r = self.session.get(url, timeout=15)
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

    def _crawl_from_urls(self) -> None:
        print("\n📄 국토부 정책 페이지 (LTV 문맥 수집)...")
        for path in MOLIT_POLICY_PATHS:
            html = self._fetch_html(path)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            text = self._soup_text(soup)
            self._text_chunks.append(text)
            self._sources.append(self.base_url + path)
            print(f"   · {path} (본문 {len(text)}자)")
            time.sleep(0.35)

    def _crawl_from_search(self) -> None:
        print("\n🔍 국토부 통합검색 보조 (LTV)...")
        for keyword in ("LTV 주택담보대출", "생애최초 LTV", "규제지역 LTV"):
            try:
                r = self.session.get(
                    f"{self.base_url}/search/search.jsp",
                    params={"query": keyword},
                    timeout=12,
                )
                r.encoding = r.apparent_encoding or "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")
                acc = ""
                for el in soup.find_all(["div", "li", "p", "td"])[:400]:
                    frag = _norm_whitespace(el.get_text(separator=" ", strip=True))
                    if len(frag) < 25:
                        continue
                    if "LTV" not in frag and "생애최초" not in frag:
                        continue
                    acc += " " + frag
                if acc:
                    self._text_chunks.append(acc)
                    self._sources.append(f"{self.base_url}/search/search.jsp?q={keyword}")
                time.sleep(0.6)
            except Exception as e:
                print(f"   ⚠️ 검색 보조 실패 ({keyword}): {e}")

    @staticmethod
    def _load_baseline_json(path: Path) -> Dict[str, Any]:
        if path.is_file():
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        raise FileNotFoundError(f"baseline JSON 없음 또는 형식 오류: {path}")

    @staticmethod
    def _extract_candidate_ltvs(text: str) -> Dict[str, int]:
        """
        보수적으로 사용할 수 있는 후보만 추출:
        - 생애최초 80
        - 일반/규제지역 40~70
        """
        found: Dict[str, int] = {}
        for m in re.finditer(r"(생애최초|무주택).{0,40}?(\d{1,2})\s*%", text):
            v = int(m.group(2))
            if 0 < v <= 100:
                found["first_home"] = max(found.get("first_home", 0), v)
        for m in re.finditer(r"(?:LTV|담보인정비율).{0,20}?(\d{1,2})\s*%", text, re.I):
            v = int(m.group(1))
            if 40 <= v <= 90:
                found["generic"] = max(found.get("generic", 0), v)
        return found

    @staticmethod
    def _apply_ltv_patch(base: Dict[str, Any], cands: Dict[str, int]) -> None:
        rules = base.get("rules")
        if not isinstance(rules, dict):
            return

        first_home_v = cands.get("first_home")
        generic_v = cands.get("generic")

        if first_home_v is not None:
            # 생애최초 키만 제한적으로 갱신
            for reg in ("투기과열지구", "조정대상지역", "일반지역"):
                r = rules.get(reg)
                if not isinstance(r, dict):
                    continue
                below = r.get("below_threshold")
                if isinstance(below, dict):
                    for key in ("무주택_생애최초", "생애최초"):
                        item = below.get(key)
                        if isinstance(item, dict) and isinstance(item.get("ltv"), (int, float)):
                            item["ltv"] = min(max(int(first_home_v), 0), 100)

        if generic_v is not None:
            # 일반 값은 일반지역 일반 항목만 보수적으로 반영
            gen = rules.get("일반지역")
            if isinstance(gen, dict):
                for block_key in ("below_threshold", "above_threshold"):
                    block = gen.get(block_key)
                    if not isinstance(block, dict):
                        continue
                    item = block.get("일반")
                    if isinstance(item, dict) and isinstance(item.get("ltv"), (int, float)):
                        item["ltv"] = min(max(int(generic_v), 0), 100)

    def crawl_ltv_rules(self) -> Dict[str, Any]:
        print("🔍 LTV 규칙 크롤링 시작...")
        self._sources = []
        self._text_chunks = []

        self._crawl_from_urls()
        self._crawl_from_search()

        combined = _norm_whitespace(" ".join(self._text_chunks))
        print(f"\n📎 수집 본문 합계: {len(combined)}자")

        candidates = self._extract_candidate_ltvs(combined)
        print(f"   추출 LTV 후보: {candidates or '(없음)'}")

        baseline_path = Path(
            os.environ.get("LTV_BASELINE_JSON", str(DEFAULT_BASELINE_JSON))
        )
        out = copy.deepcopy(self._load_baseline_json(baseline_path))
        out["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        prev = str(out.get("source", ""))
        out["source"] = f"{prev}; 웹크롤 병합 ({datetime.now().date()})".strip("; ")

        if candidates:
            self._apply_ltv_patch(out, candidates)

        out["crawl_meta"] = {
            "generated_at": datetime.now().isoformat(),
            "baseline": str(baseline_path.resolve()),
            "sources": self._sources[:25],
            "extracted_ltv_candidates": candidates,
        }
        print("\n✅ LTV 크롤·병합 완료")
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
            os.environ["LTV_BASELINE_JSON"] = str(Path(baseline_json).resolve())

        if run_crawl:
            result = self.crawl_ltv_rules()
        else:
            baseline_path = Path(
                os.environ.get("LTV_BASELINE_JSON", str(DEFAULT_BASELINE_JSON))
            )
            result = self._load_baseline_json(baseline_path)

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n💾 {out_path.resolve()} 저장 완료")
        return str(out_path.resolve())


def run() -> None:
    crawler = LtvRulesCrawler()
    crawler.save_to_json()


if __name__ == "__main__":
    run()
