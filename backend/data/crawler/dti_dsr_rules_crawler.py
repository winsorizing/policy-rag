# backend/data/crawler/dti_dsr_rules_crawler.py
#
# - 로컬: 금융위 등 「가계부채 관리 강화 방안」 보도자료 PDF(예: 250627) 텍스트 추출 → DTI/DSR 문맥·notes 보강
# - 선택: KB Think 「LTV, DTI, DSR」 가이드 웹 본문과 합산 후 정규식으로 수치 힌트 추출
#
# 실행 (backend 디렉터리):
#   python data/crawler/dti_dsr_rules_crawler.py
#   python data/crawler/dti_dsr_rules_crawler.py --pdf-only
#   python data/crawler/dti_dsr_rules_crawler.py --no-web
#
# 환경변수:
#   DTI_DSR_PRESS_PDF   보도자료 PDF 경로(미설정 시 아래 DEFAULT_PRESS_PDF)
#   DTI_DSR_SKIP_WEB=1     웹 크롤 생략(PDF만)
#   DTI_DSR_WEB_URL        웹 본문 URL (기본: KB Think LTV·DTI·DSR 가이드)
# https://www.fsc.go.kr/no010101/85476?srchCtgry=&curPage=&srchKey=sj&srchText=LTV&srchBeginDt=&srchEndDt=
# https://kbthink.com/loan-guide/ltv-dti-dsr.html
# https://www.fsc.go.kr/no010101/84824?srchCtgry=&curPage=&srchKey=&srchText=&srchBeginDt=&srchEndDt

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------

_CRAWLER_DIR = Path(__file__).resolve().parent
_DATA_DIR = _CRAWLER_DIR.parent

DEFAULT_BASELINE_JSON = _DATA_DIR / "rules" / "manual" / "dti_dsr_rules.json"
DEFAULT_OUTPUT_JSON = _DATA_DIR / "rules" / "crawled" / "dti_dsr_rules.json"
DEFAULT_PRESS_PDF = _CRAWLER_DIR / "pdf" / "250627(보도자료)가계부채 관리 방안.pdf"

# KB Think — LTV·DTI·DSR 설명 및 지역별 요약 표 (정보 제공용; 최종 규정은 금융사·고시 확인)
DEFAULT_WEB_GUIDE_URL = "https://kbthink.com/loan-guide/ltv-dti-dsr.html"

_EMBEDDED_BASELINE: Dict[str, Any] = {
    "last_updated": "2024-05-08",
    "source": "금융위원회 고시",
    "dti_rules": {
        "투기과열지구": {"0주택": 40, "1주택": 40, "2주택": 40, "3주택_이상": 0},
        "조정대상지역": {"0주택": 50, "1주택": 50, "2주택": 40, "3주택_이상": 0},
        "일반지역": {"전체": 60},
    },
    "dsr_rules": {
        "기본": {"limit": 40, "condition": "연소득 1.5억 미만"},
        "고소득자": {"limit": 50, "condition": "연소득 1.5억 이상"},
    },
    "notes": {
        "DTI": "총부채상환비율 = (연간 주택담보대출 원리금상환액 / 연소득) × 100",
        "DSR": "총부채원리금상환비율 = (연간 모든 대출 원리금상환액 / 연소득) × 100",
    },
}


def _norm_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip()


def _extract_text_from_pdf(path: Path) -> str:
    """pypdf로 전 페이지 텍스트 추출. 미설치 시 RuntimeError."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError(
            "PDF 텍스트 추출에 pypdf 가 필요합니다. backend 에서: pip install pypdf"
        ) from e

    reader = PdfReader(str(path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        parts.append(raw)
    return _norm_whitespace("\n".join(parts))


def _apply_pdf_context_notes(base: Dict[str, Any], pdf_text: str) -> None:
    """
    「가계부채 관리 강화 방안」 보도자료(2025.6.27) 본문에서 DTI/DSR·한도 관련 서술을 notes에 반영.
    (표 형태의 지역별 DTI%는 본 PDF에 없으므로 수치 규칙은 웹 추출·베이스라인에 의존)
    """
    notes = base.setdefault("notes", {})
    if not isinstance(notes, dict):
        return
    t = _norm_whitespace(pdf_text)
    if not t:
        return

    if "6억원" in t and ("DTI" in t or "DSR" in t or "dti" in t.lower()):
        notes["주담대_취급한도_산정"] = (
            "수도권·규제지역 주택구입목적 주담대 최대한도 6억원; "
            "실제 대출금액은 한도 내에서 LTV·DTI·DSR 비율 등에 따라 달라질 수 있음. "
            "(금융위 등 「가계부채 관리 강화 방안」 보도자료, '25.6.27.)"
        )

    if "30년" in t and "DSR" in t:
        notes["DSR_만기_보완취지"] = (
            "수도권·규제지역 내 주담대 만기를 30년 이내로 제한하여 DSR 규제 우회를 방지. 시행 '25.6.28. "
            "(동 보도자료)"
        )

    if "신용대출" in t and "연소득" in t:
        notes["신용대출_한도"] = (
            "신용대출 한도를 차주별 연소득 이내로 제한(수도권·규제지역 중심 가계부채 관리). 시행 '25.6.28. "
            "(동 보도자료; DSR 산정과 연계된 총부채 관리 취지)"
        )


class DtiDsrRulesCrawler:
    """보도자료 PDF + (선택) KB Think LTV·DTI·DSR 가이드 웹 본문에서 힌트를 추출해 dti_dsr_rules.json 스키마로 저장."""

    def __init__(self) -> None:
        self.web_guide_url = os.environ.get("DTI_DSR_WEB_URL", DEFAULT_WEB_GUIDE_URL).strip()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://kbthink.com/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        self._sources: List[str] = []
        self._text_chunks: List[str] = []
        self._press_pdf_meta: Dict[str, Any] = {}

    def _fetch_html(self, base: str, path: str) -> str | None:
        url = f"{base}{path}" if path.startswith("/") else path
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

    def _crawl_from_press_pdf(self, pdf_path: Path | None) -> str:
        """로컬 보도자료 PDF. 없거나 실패 시 빈 문자열."""
        path = pdf_path
        if path is None:
            env = os.environ.get("DTI_DSR_PRESS_PDF")
            path = Path(env) if env else DEFAULT_PRESS_PDF

        self._press_pdf_meta = {"path": str(path.resolve()), "used": False, "chars": 0, "error": None}

        if not path.is_file():
            print(f"\n📎 보도자료 PDF 없음(건너뜀): {path}")
            self._press_pdf_meta["error"] = "file_not_found"
            return ""

        print(f"\n📎 보도자료 PDF 로드: {path.name}")
        try:
            text = _extract_text_from_pdf(path)
        except Exception as e:
            print(f"   ⚠️ PDF 추출 실패: {e}")
            self._press_pdf_meta["error"] = str(e)
            return ""

        self._text_chunks.append(text)
        self._sources.append(f"file://{path.resolve()}")
        self._press_pdf_meta["used"] = True
        self._press_pdf_meta["chars"] = len(text)
        print(f"   · 추출 본문 {len(text)}자")
        return text

    def _crawl_from_web_guide(self, url: str | None = None) -> None:
        """KB Think 등 단일 HTML 가이드 페이지 본문 수집."""
        target = (url or self.web_guide_url).strip()
        if not target:
            print("\n⚠️ 웹 가이드 URL이 비어 있어 건너뜁니다.")
            return

        print(f"\n🌐 웹 가이드 수집: {target}")
        html = self._fetch_html("", target)
        if not html:
            return
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = self._soup_text(soup)
        self._text_chunks.append(text)
        self._sources.append(target)
        print(f"   · 본문 {len(text)}자")
        time.sleep(0.35)

    @staticmethod
    def _extract_dti_kbthink_table(text: str) -> Dict[str, int]:
        """
        KB Think 글 내 표·문장 형태(예: 투기지역 및 투기과열지구 40%, 조정대상지역 50%)에서 DTI 후보 추출.
        기존 _extract_dti_by_region과 병합 시 빈 키만 채우거나 수치가 있으면 보강.
        """
        out: Dict[str, int] = {}
        t = _norm_whitespace(text)

        m_pair = re.search(
            r"투기지역\s*및\s*투기과열지구\s*(\d{1,2})\s*%.*?조정대상지역\s*(\d{1,2})\s*%",
            t,
            flags=re.DOTALL,
        )
        if m_pair:
            a, b = int(m_pair.group(1)), int(m_pair.group(2))
            if 0 < a <= 100:
                out["투기과열지구"] = a
            if 0 < b <= 100:
                out["조정대상지역"] = b
        else:
            m_hot = re.search(r"(?:투기지역\s*및\s*)?투기과열지구\s*(\d{1,2})\s*%", t)
            if m_hot:
                v = int(m_hot.group(1))
                if 0 < v <= 100:
                    out["투기과열지구"] = v
            m_adj = re.search(r"조정대상지역\s*(\d{1,2})\s*%", t)
            if m_adj:
                v = int(m_adj.group(1))
                if 0 < v <= 100:
                    out["조정대상지역"] = v

        # "기타지역 생애최초 80% 60%" → 두 번째 %가 DTI(첫 번째는 LTV)
        m_ot = re.search(r"기타지역\s*생애최초\s*(\d{1,2})\s*%\s*(\d{1,2})\s*%", t)
        if m_ot:
            dti_val = int(m_ot.group(2))
            if 0 < dti_val <= 100:
                out["일반지역"] = dti_val

        return out

    @staticmethod
    def _apply_kbthink_dsr_note(base: Dict[str, Any], text: str) -> None:
        """KB 글의 '대출금액 1억 초과 시 DSR 40%' 등은 소득구간 한도와 달라 notes에만 기록."""
        t = _norm_whitespace(text)
        if "DSR" not in t:
            return
        notes = base.setdefault("notes", {})
        if not isinstance(notes, dict):
            return
        if re.search(r"1억원?\s*(?:을\s*)?초과", t) and re.search(r"DSR\s*40\s*%", t, re.I):
            notes["DSR_KB참고_대출금액구간"] = (
                "KB Think 안내: 대출금액 1억원 초과 구간에 DSR 40% 규제가 적용된다는 설명이 있음. "
                "1억원 미만은 상품별로 상이할 수 있음. 실제 심사는 금융기관·당시 고시 기준을 확인할 것. "
                f"(출처: {DEFAULT_WEB_GUIDE_URL})"
            )

    @staticmethod
    def _first_percent_after_anchor(
        text: str, anchor: str, labels: Tuple[str, ...], window: int = 420
    ) -> int | None:
        idx = text.find(anchor)
        if idx < 0:
            return None
        chunk = text[idx : idx + window]
        for lab in labels:
            j = chunk.find(lab)
            if j < 0:
                continue
            sub = chunk[j : j + 120]
            m = re.search(r"(\d{1,2})\s*%", sub)
            if m:
                v = int(m.group(1))
                if 0 < v <= 100:
                    return v
        m2 = re.search(r"(?:DTI|dti)\s*[∶:]?\s*(\d{1,2})\s*%", chunk)
        if m2:
            v = int(m2.group(1))
            if 0 < v <= 100:
                return v
        return None

    def _extract_dti_by_region(self, text: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        hot = self._first_percent_after_anchor(
            text, "투기과열", ("DTI", "dti", "원리금", "상환비율")
        )
        if hot is None:
            hot = self._first_percent_after_anchor(text, "투기지역", ("DTI", "dti"))
        if hot is not None:
            out["투기과열지구"] = hot

        adj = self._first_percent_after_anchor(
            text, "조정대상", ("DTI", "dti", "원리금", "상환비율")
        )
        if adj is not None:
            out["조정대상지역"] = adj

        for anchor in ("일반지역", "비규제", "규제지역 외"):
            if anchor not in text:
                continue
            g = self._first_percent_after_anchor(text, anchor, ("DTI", "dti"))
            if g is not None:
                out["일반지역"] = g
                break
        return out

    @staticmethod
    def _extract_dsr_limits(text: str) -> Tuple[int | None, int | None]:
        basic: int | None = None
        high: int | None = None
        for pat in (
            r"1\.?\s*5\s*억\s*미만.{0,120}?DSR.{0,25}?(\d{1,2})\s*%",
            r"DSR.{0,40}?1\.?\s*5\s*억\s*미만.{0,80}?(\d{1,2})\s*%",
            r"연소득\s*1\.?\s*5\s*억\s*미만.{0,100}?(\d{1,2})\s*%\s*(?:이내|한도|적용)",
        ):
            m = re.search(pat, text, re.I)
            if m:
                v = int(m.group(1))
                if 0 < v <= 100:
                    basic = v
                    break
        for pat in (
            r"1\.?\s*5\s*억\s*이상.{0,120}?DSR.{0,25}?(\d{1,2})\s*%",
            r"DSR.{0,40}?1\.?\s*5\s*억\s*이상.{0,80}?(\d{1,2})\s*%",
            r"연소득\s*1\.?\s*5\s*억\s*이상.{0,100}?(\d{1,2})\s*%\s*(?:이내|한도|적용)",
        ):
            m = re.search(pat, text, re.I)
            if m:
                v = int(m.group(1))
                if 0 < v <= 100:
                    high = v
                    break
        if basic is None or high is None:
            # KB Think 등: 대출금액 1억 초과 시 DSR 40% 문구는 연소득 구간 한도와 혼동되므로 숫자 폴백 생략
            if re.search(r"1억원?\s*(?:을\s*)?초과", text) and re.search(r"DSR\s*40\s*%", text, re.I):
                return basic, high
            pairs = re.findall(r"DSR\s*[∶:]?\s*(\d{1,2})\s*%", text, flags=re.I)
            nums = sorted({int(x) for x in pairs if 0 < int(x) <= 100})
            if len(nums) >= 2 and basic is None and high is None:
                basic, high = nums[0], nums[-1]
            elif len(nums) == 1 and basic is None and high is None:
                basic = nums[0]
        return basic, high

    @staticmethod
    def _load_baseline_json(path: Path) -> Dict[str, Any]:
        if path.is_file():
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        return copy.deepcopy(_EMBEDDED_BASELINE)

    @staticmethod
    def _apply_dti_patch(base: Dict[str, Any], dti_found: Dict[str, int]) -> None:
        dti = base.setdefault("dti_rules", {})
        if "투기과열지구" in dti_found and isinstance(dti.get("투기과열지구"), dict):
            v = dti_found["투기과열지구"]
            for k in ("0주택", "1주택", "2주택"):
                dti["투기과열지구"][k] = v
        if "조정대상지역" in dti_found and isinstance(dti.get("조정대상지역"), dict):
            v = dti_found["조정대상지역"]
            for k in ("0주택", "1주택"):
                dti["조정대상지역"][k] = v
        if "일반지역" in dti_found and isinstance(dti.get("일반지역"), dict):
            dti["일반지역"]["전체"] = dti_found["일반지역"]

    @staticmethod
    def _apply_dsr_patch(base: Dict[str, Any], basic: int | None, high: int | None) -> None:
        dsr = base.setdefault("dsr_rules", {})
        if basic is not None and isinstance(dsr.get("기본"), dict):
            dsr["기본"]["limit"] = basic
        if high is not None and isinstance(dsr.get("고소득자"), dict):
            dsr["고소득자"]["limit"] = high

    def crawl_dti_dsr_rules(
        self,
        *,
        include_web: bool = True,
        press_pdf: Path | None = None,
        use_press_pdf: bool = True,
        web_guide_url: str | None = None,
    ) -> Dict[str, Any]:
        print("🔍 DTI/DSR 규칙 수집 시작...")
        self._sources = []
        self._text_chunks = []
        self._press_pdf_meta = {}

        pdf_text = ""
        if use_press_pdf:
            pdf_text = self._crawl_from_press_pdf(press_pdf)

        guide_url = (web_guide_url or self.web_guide_url).strip()
        if include_web:
            self._crawl_from_web_guide(guide_url)
        else:
            print("\nℹ️ 웹 크롤 생략(include_web=False 또는 DTI_DSR_SKIP_WEB)")

        combined = _norm_whitespace(" ".join(self._text_chunks))
        print(f"\n📎 수집 본문 합계: {len(combined)}자")

        dti_generic = self._extract_dti_by_region(combined)
        dti_kb = self._extract_dti_kbthink_table(combined)
        dti_found: Dict[str, int] = {**dti_generic}
        for k, v in dti_kb.items():
            dti_found[k] = v

        dsr_basic, dsr_high = self._extract_dsr_limits(combined)
        print(f"   추출 DTI 후보: {dti_found or '(없음)'}")
        print(f"   추출 DSR 후보: 기본={dsr_basic}, 고소득={dsr_high}")

        baseline_path = Path(
            os.environ.get("DTI_DSR_BASELINE_JSON", str(DEFAULT_BASELINE_JSON))
        )
        out = self._load_baseline_json(baseline_path)
        out["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        prev = str(out.get("source", ""))
        parts_src = [prev] if prev else []
        if pdf_text:
            parts_src.append("가계부채 관리 강화 방안 보도자료(PDF)")
        if include_web and guide_url:
            parts_src.append(f"KB Think 가이드 웹 ({guide_url})")
        out["source"] = "; ".join(p for p in parts_src if p).strip("; ")

        if pdf_text:
            _apply_pdf_context_notes(out, pdf_text)
        if include_web:
            self._apply_kbthink_dsr_note(out, combined)

        if dti_found:
            self._apply_dti_patch(out, dti_found)
        if dsr_basic is not None or dsr_high is not None:
            self._apply_dsr_patch(out, dsr_basic, dsr_high)

        out["crawl_meta"] = {
            "generated_at": datetime.now().isoformat(),
            "baseline": str(baseline_path.resolve()),
            "web_guide_url": guide_url if include_web else None,
            "sources": self._sources[:40],
            "press_pdf": dict(self._press_pdf_meta),
            "extracted_dti": dti_found,
            "extracted_dsr": {"기본": dsr_basic, "고소득자": dsr_high},
        }

        print("\n✅ DTI/DSR 수집·병합 완료")
        return out

    def save_to_json(
        self,
        output_file: str | Path | None = None,
        *,
        run_crawl: bool = True,
        baseline_json: str | Path | None = None,
        include_web: bool | None = None,
        press_pdf: Path | None = None,
        use_press_pdf: bool = True,
        web_guide_url: str | None = None,
    ) -> str:
        out_path = Path(output_file) if output_file else DEFAULT_OUTPUT_JSON
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if baseline_json:
            os.environ["DTI_DSR_BASELINE_JSON"] = str(Path(baseline_json).resolve())

        if include_web is None:
            include_web = os.environ.get("DTI_DSR_SKIP_WEB", "").strip() not in (
                "1",
                "true",
                "yes",
            )

        if run_crawl:
            result = self.crawl_dti_dsr_rules(
                include_web=include_web,
                press_pdf=press_pdf,
                use_press_pdf=use_press_pdf,
                web_guide_url=web_guide_url,
            )
        else:
            baseline_path = Path(
                os.environ.get("DTI_DSR_BASELINE_JSON", str(DEFAULT_BASELINE_JSON))
            )
            result = self._load_baseline_json(baseline_path)

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n💾 {out_path.resolve()} 저장 완료")
        return str(out_path.resolve())


def run() -> None:
    parser = argparse.ArgumentParser(description="DTI/DSR 규칙: 보도자료 PDF + 선택적 웹 크롤")
    parser.add_argument(
        "--pdf-path",
        type=Path,
        default=None,
        help=f"보도자료 PDF 경로 (기본: {DEFAULT_PRESS_PDF.name})",
    )
    parser.add_argument(
        "--pdf-only",
        "--no-web",
        dest="pdf_only",
        action="store_true",
        help="웹 요청 없이 PDF만 사용",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="로컬 PDF 생략(웹만)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help=f"출력 JSON (기본: {DEFAULT_OUTPUT_JSON})",
    )
    parser.add_argument(
        "--web-url",
        type=str,
        default=None,
        help=f"웹 가이드 URL (기본: {DEFAULT_WEB_GUIDE_URL})",
    )
    args = parser.parse_args()

    if args.web_url:
        os.environ["DTI_DSR_WEB_URL"] = args.web_url.strip()

    crawler = DtiDsrRulesCrawler()
    crawler.save_to_json(
        args.output,
        baseline_json=str(args.baseline) if args.baseline else None,
        include_web=not args.pdf_only,
        press_pdf=args.pdf_path,
        use_press_pdf=not args.no_pdf,
        web_guide_url=args.web_url,
    )


if __name__ == "__main__":
    run()
