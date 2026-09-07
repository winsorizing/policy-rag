from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

# 국토부 본문: "(서울) 全 지역", "서울 전 지역", "(경기) 全 지역(일부 지역* 제외) * 김포, … (인천) 全 지역(…)" 등
_WHOLE_WORD = r"(?:전\s*지역|全\s*지역|전역|전체(?:\s*지역)?)"
METRO_WHOLE_SEOUL_RE = re.compile(
    rf"(?:\(\s*서울\s*\)\s*|서울특별시|서울시|서울)\s*{_WHOLE_WORD}"
)
METRO_WHOLE_GYEONGGI_TRIGGER_RE = re.compile(
    rf"(?:\(\s*경기\s*\)\s*|경기도|경기)\s*{_WHOLE_WORD}"
)
METRO_WHOLE_INCHEON_RE = re.compile(
    rf"(?:\(\s*인천\s*\)\s*|인천광역시|인천시|인천)\s*{_WHOLE_WORD}"
)
METRO_LOCAL_BLOCK_RE = re.compile(r"\(\s*지방\s*\)")


def _norm_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip()


# 서울 25개 자치구 (규제지역 JSON과 동일: "서울특별시 {구}")
SEOUL_ALL_DISTRICTS: frozenset[str] = frozenset(
    f"서울특별시 {gu}"
    for gu in (
        "종로구",
        "중구",
        "용산구",
        "성동구",
        "광진구",
        "동대문구",
        "중랑구",
        "성북구",
        "강북구",
        "도봉구",
        "노원구",
        "은평구",
        "서대문구",
        "마포구",
        "양천구",
        "강서구",
        "구로구",
        "금천구",
        "영등포구",
        "동작구",
        "관악구",
        "서초구",
        "강남구",
        "송파구",
        "강동구",
    )
)

# 경기도 시·군·구 단위 전체 (행정안전부 기준 시군구 편제, 규제 문서에서 쓰는 "경기도 …" 표기와 맞춤)
_GYEONGGI_PARTS: tuple[str, ...] = (
    "수원시 장안구",
    "수원시 권선구",
    "수원시 팔달구",
    "수원시 영통구",
    "성남시 수정구",
    "성남시 중원구",
    "성남시 분당구",
    "의정부시",
    "안양시 만안구",
    "안양시 동안구",
    "부천시 원미구",
    "부천시 소사구",
    "부천시 오정구",
    "광명시",
    "평택시",
    "동두천시",
    "안산시 상록구",
    "안산시 단원구",
    "고양시 덕양구",
    "고양시 일산동구",
    "고양시 일산서구",
    "과천시",
    "구리시",
    "남양주시",
    "오산시",
    "시흥시",
    "군포시",
    "의왕시",
    "하남시",
    "용인시 처인구",
    "용인시 기흥구",
    "용인시 수지구",
    "파주시",
    "이천시",
    "안성시",
    "김포시",
    "화성시",
    "광주시",
    "여주시",
    "양평군",
    "연천군",
    "가평군",
    "양주시",
    "포천시",
)
GYEONGGI_ALL_UNITS: frozenset[str] = frozenset(f"경기도 {p}" for p in _GYEONGGI_PARTS)

# "김포, 파주 …" 등 본문 짧은 호칭 → 전체 집합에서 제외할 정식명
GYEONGGI_SIMPLE_EXCLUDE_ALIASES: dict[str, str] = {
    "김포": "경기도 김포시",
    "김포시": "경기도 김포시",
    "파주": "경기도 파주시",
    "파주시": "경기도 파주시",
    "연천": "경기도 연천군",
    "연천군": "경기도 연천군",
    "동두천": "경기도 동두천시",
    "동두천시": "경기도 동두천시",
    "포천": "경기도 포천시",
    "포천시": "경기도 포천시",
    "가평": "경기도 가평군",
    "가평군": "경기도 가평군",
    "양평": "경기도 양평군",
    "양평군": "경기도 양평군",
    "여주": "경기도 여주시",
    "여주시": "경기도 여주시",
    "이천": "경기도 이천시",
    "이천시": "경기도 이천시",
}

# 규제 문서에서 흔한 '인천 전 지역(강화·옹진 제외)' = 광역시 8개 자치구
INCHEON_METRO_GU: frozenset[str] = frozenset(
    f"인천광역시 {g}"
    for g in ("중구", "동구", "미추홀구", "연수구", "남동구", "부평구", "계양구", "서구")
)

DAEJEON_ALL_DISTRICTS: frozenset[str] = frozenset(
    f"대전광역시 {g}" for g in ("동구", "중구", "서구", "유성구", "대덕구")
)

# 청주 동·읍 세부는 JSON에 담기 어려워 4개 구를 보수적으로 포함(문서·지도로 재확인 권장)
CHEONGJU_CITY_DISTRICTS: frozenset[str] = frozenset(
    f"충청북도 청주시 {gu}" for gu in ("상당구", "서원구", "흥덕구", "청원구")
)


def _truncate_region_note(s: str, max_len: int = 220) -> str:
    s = _norm_whitespace(s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _first_balanced_paren_content(s: str) -> str:
    i = s.find("(")
    if i < 0:
        return ""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j].strip()
    return ""


def _split_top_level_commas(s: str) -> List[str]:
    """괄호 안 쉼표는 유지하고, 최상위만 `,`·`，`·`·`(김포·파주 나열용)으로 분리."""
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch in (",", "，") and depth == 0:
            t = "".join(buf).strip()
            if t:
                parts.append(t)
            buf = []
        elif ch == "·" and depth == 0:
            t = "".join(buf).strip()
            if t:
                parts.append(t)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _gyeonggi_exclusion_chunk_after_trigger(t: str, trigger_end: int) -> str:
    """'(경기) 全 … (일부 지역* 제외) * …' 에서 별 뒤 목록만 추출. 없으면 ''."""
    tail = t[trigger_end:].lstrip()
    tail = re.sub(r"^\(\s*일부\s*지역\s*\*\s*제외\s*\)\s*", "", tail, count=1)
    if not tail.startswith("*"):
        return ""
    rest = tail[1:].lstrip()
    boundary = re.search(r"\s*\(\s*(?:인천|서울|경기|지방)\s*\)", rest)
    if boundary:
        return rest[: boundary.start()].strip()
    return rest.strip()


def _apply_one_gyeonggi_exclude_token(units: Set[str], seg: str) -> None:
    """경기 전체 집합에서 시·군 단위 제거 또는 '일부 읍·면 제외' 주석 행으로 치환."""
    seg = seg.strip()
    if not seg:
        return

    if seg.startswith("용인처인") or re.match(r"^용인시\s*처인", seg):
        units.discard("경기도 용인시 처인구")
        inner = _first_balanced_paren_content(seg) or seg
        units.add(
            _truncate_region_note(f"경기도 용인시 처인구 (일부 읍·면 제외: {inner})")
        )
        return
    if re.match(r"^광주\s*\(", seg):
        units.discard("경기도 광주시")
        inner = _first_balanced_paren_content(seg) or seg
        units.add(_truncate_region_note(f"경기도 광주시 (일부 읍·면 제외: {inner})"))
        return
    if re.match(r"^남양주\s*\(", seg):
        units.discard("경기도 남양주시")
        inner = _first_balanced_paren_content(seg) or seg
        units.add(_truncate_region_note(f"경기도 남양주시 (일부 읍·면 제외: {inner})"))
        return
    if re.match(r"^안성\s*\(", seg):
        units.discard("경기도 안성시")
        inner = _first_balanced_paren_content(seg) or seg
        units.add(_truncate_region_note(f"경기도 안성시 (일부 읍·면 제외: {inner})"))
        return

    head = re.split(r"\s*\(", seg, maxsplit=1)[0].strip()
    if not head:
        return
    # 긴 별칭(예: '동두천시 일부')은 시·군 단위만 매칭
    for alias, full in GYEONGGI_SIMPLE_EXCLUDE_ALIASES.items():
        if head == alias or head.startswith(f"{alias} "):
            units.discard(full)
            return


def _gyeonggi_units_from_text(t: str) -> Set[str]:
    m = METRO_WHOLE_GYEONGGI_TRIGGER_RE.search(t)
    if not m:
        return set()
    units: Set[str] = set(GYEONGGI_ALL_UNITS)
    chunk = _gyeonggi_exclusion_chunk_after_trigger(t, m.end())
    if chunk:
        for seg in _split_top_level_commas(chunk):
            _apply_one_gyeonggi_exclude_token(units, seg)
    return units


def _incheon_units_from_text(t: str) -> Set[str]:
    if not METRO_WHOLE_INCHEON_RE.search(t):
        return set()
    # '강화·옹진 제외' 등은 통상 8개 구만 규제권역으로 쓰이므로 군 지역은 넣지 않음
    return set(INCHEON_METRO_GU)


def _local_block_body(t: str) -> Optional[str]:
    m = METRO_LOCAL_BLOCK_RE.search(t)
    if not m:
        return None
    return t[m.end() :].strip()


def _local_block_units_from_text(t: str) -> Set[str]:
    body = _local_block_body(t)
    if not body:
        return set()
    # 다음 괄호 블록 전까지만 (한 줄 가정)
    end_m = re.search(r"\(\s*(?:서울|경기|인천)\s*\)\s*(?:전|全)", body)
    slice_end = end_m.start() if end_m else len(body)
    body = body[:slice_end].strip()
    out: Set[str] = set()
    if re.search(r"세종", body) and re.search(r"행복", body):
        out.add("세종특별자치시 (행복도시 예정지역만 규제 적용)")
    if re.search(r"(?:^|(?<=[,，\s]))대전(?=[,，\s]|$)", body):
        out.update(DAEJEON_ALL_DISTRICTS)
    if "청주" in body:
        out.update(CHEONGJU_CITY_DISTRICTS)
    return out


def _districts_from_whole_metro_phrases_static(text: str) -> Set[str]:
    """괄호·전(全) 지역·제외 목록·(지방) 블록까지 반영."""
    out: Set[str] = set()
    if METRO_WHOLE_SEOUL_RE.search(text):
        out.update(SEOUL_ALL_DISTRICTS)
    out.update(_gyeonggi_units_from_text(text))
    out.update(_incheon_units_from_text(text))
    out.update(_local_block_units_from_text(text))
    return out


# 본문에서 바로 잡히는 완전한 행정구역 문자열 (수동 regulation_areas.json 과 동일 스타일)
DISTRICT_RE = re.compile(
    r"(?:서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시)\s+[가-힣]+구|"
    r"세종특별자치시|"
    r"(?:경기도|강원특별자치도|충청북도|충청남도|전북특별자치도|전라남도|경상북도|경상남도|제주특별자치도)\s+"
    r"(?:[가-힣]+(?:시|군)(?:\s+[가-힣]+구)?|[가-힣]+구)"
)

# 규제지역 설명이 있을 만한 페이지 (메인만 보면 지역 목록이 거의 없음)
DEFAULT_FALLBACK_JSON = (
    Path(__file__).resolve().parent.parent / "rules" / "manual" / "regulation_areas.json"
)

REGULATION_SOURCE_PATHS = [
    "/policy/main.jsp",
    "/policy/stable/sta_b_03.jsp",
    "/policy/stable/sta_b_02.jsp",
    "/policy/stable/sta_a_01.jsp",
    "/policy/stable/sta_b_01.jsp",
]


class MOLITRegulationCrawler:
    """국토교통부 규제지역 크롤러 (HTML 본문 구간 + 표 + 행정구역 정규식)"""

    def __init__(self) -> None:
        self.base_url = "https://www.molit.go.kr"
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
        self.regulation_data: Dict[str, Set[str] | List[str]] = {
            "투기과열지구": set(),
            "조정대상지역": set(),
            "일반지역": [],
        }

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

    @staticmethod
    def _is_valid_region(region: str) -> bool:
        # '일부 읍·면 제외' 등 긴 주석 행은 220자 내외로 잘리므로 상한을 넉넉히 둠
        if not region or len(region) < 4 or len(region) > 260:
            return False
        if re.search(r"[0-9]", region):
            return False
        if not re.search(r"(시|군|구|도|특별자치시)", region):
            return False
        return True

    @staticmethod
    def _districts_from_whole_metro_phrases(text: str) -> Set[str]:
        """(서울)/(경기)/(인천)/(지방) 표기, 경기 제외 목록·읍면별 제외 주석 등."""
        return _districts_from_whole_metro_phrases_static(text)

    def _districts_from_text(self, text: str) -> Set[str]:
        t = _norm_whitespace(text)
        found = {m for m in DISTRICT_RE.findall(t) if self._is_valid_region(m)}
        found.update(self._districts_from_whole_metro_phrases(t))
        return found

    def _split_hot_adj_chunks(self, text: str) -> Tuple[str, str]:
        """키워드 위치로 구간 나눔. 둘 다 없으면 ('', 전체)."""
        t = _norm_whitespace(text)
        if not t:
            return "", ""

        def first_pos(keys: Tuple[str, ...]) -> int:
            pos = -1
            for k in keys:
                i = t.find(k)
                if i >= 0 and (pos < 0 or i < pos):
                    pos = i
            return pos

        i_hot = first_pos(("투기과열지구", "투기과열지역", "투기과열"))
        i_adj = first_pos(("조정대상지역", "조정대상"))

        if i_hot < 0 and i_adj < 0:
            return "", t

        limit = 50000
        hot_chunk = ""
        adj_chunk = ""

        if i_hot >= 0 and i_adj >= 0:
            if i_hot < i_adj:
                hot_chunk = t[i_hot : i_adj]
                adj_chunk = t[i_adj : min(len(t), i_adj + limit)]
            else:
                adj_chunk = t[i_adj : i_hot]
                hot_chunk = t[i_hot : min(len(t), i_hot + limit)]
        elif i_hot >= 0:
            hot_chunk = t[i_hot : min(len(t), i_hot + limit)]
        else:
            adj_chunk = t[i_adj : min(len(t), i_adj + limit)]

        return hot_chunk, adj_chunk

    def _ingest_plaintext(self, text: str) -> None:
        hot_c, adj_c = self._split_hot_adj_chunks(text)
        if hot_c:
            self.regulation_data["투기과열지구"].update(self._districts_from_text(hot_c))
        if adj_c:
            self.regulation_data["조정대상지역"].update(self._districts_from_text(adj_c))

    def _ingest_tables(self, soup: BeautifulSoup) -> None:
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if not cells:
                    continue
                row_text = " ".join(c.get_text(separator=" ", strip=True) for c in cells)
                row_text = _norm_whitespace(row_text)
                if not row_text:
                    continue
                districts = self._districts_from_text(row_text)
                if not districts:
                    continue
                if "투기과열" in row_text or "투기지구" in row_text:
                    self.regulation_data["투기과열지구"].update(districts)
                if "조정대상" in row_text:
                    self.regulation_data["조정대상지역"].update(districts)

    def _crawl_from_urls(self) -> None:
        print("\n📄 규제·정책 관련 페이지 일괄 수집...")
        for path in REGULATION_SOURCE_PATHS:
            html = self._fetch_html(path)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            text = self._soup_text(soup)
            self._ingest_plaintext(text)
            self._ingest_tables(soup)
            print(f"   · {path} 처리 (본문 길이 {len(text)}자)")
            time.sleep(0.4)

    def _crawl_from_search(self) -> None:
        print("\n🔍 통합검색 보조 (선택)...")
        keywords = ["투기과열지구", "조정대상지역"]
        for keyword in keywords:
            try:
                search_url = f"{self.base_url}/search/search.jsp"
                r = self.session.get(
                    search_url,
                    params={"query": keyword},
                    timeout=12,
                )
                r.encoding = r.apparent_encoding or "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")
                # 클래스명이 사이트 개편으로 바뀔 수 있어 넓게 탐색
                blocks = soup.find_all(["div", "li", "p", "td"])
                seen_text = ""
                for el in blocks[:400]:
                    fragment = _norm_whitespace(el.get_text(separator=" ", strip=True))
                    if len(fragment) < 30:
                        continue
                    if keyword[:4] not in fragment:
                        continue
                    seen_text += " " + fragment
                self._ingest_plaintext(seen_text)
                time.sleep(0.8)
            except Exception as e:
                print(f"   ⚠️ 검색 보조 실패 ({keyword}): {e}")

    def _dedupe_adj_vs_hot(self) -> None:
        hot: Set[str] = self.regulation_data["투기과열지구"]  # type: ignore[assignment]
        adj: Set[str] = self.regulation_data["조정대상지역"]  # type: ignore[assignment]
        adj.difference_update(hot)

    def _to_result_dict(self) -> Dict:
        hot = sorted(self.regulation_data["투기과열지구"])  # type: ignore[arg-type]
        adj = sorted(self.regulation_data["조정대상지역"])  # type: ignore[arg-type]
        return {
            "last_updated": datetime.now().isoformat(),
            "source": "국토교통부",
            "regions": {
                "투기과열지구": hot,
                "조정대상지역": adj,
                "일반지역": ["기타 모든 지역"],
            },
            "total_count": {
                "투기과열지구": len(hot),
                "조정대상지역": len(adj),
            },
        }

    def crawl_regulation_areas(self) -> Dict:
        print("🔍 국토교통부 규제지역 크롤링 시작...")
        self.regulation_data = {
            "투기과열지구": set(),
            "조정대상지역": set(),
            "일반지역": [],
        }

        self._crawl_from_urls()
        self._crawl_from_search()
        self._dedupe_adj_vs_hot()

        result = self._to_result_dict()
        print("\n✅ 크롤링 완료:")
        print(f"   투기과열지구: {result['total_count']['투기과열지구']}개")
        print(f"   조정대상지역: {result['total_count']['조정대상지역']}개")
        return result

    @staticmethod
    def _load_fallback_regions_from_json(path: Path) -> tuple[set[str], set[str]]:
        """
        JSON 형식:
        {
          "regions": {
            "투기과열지구": [...],
            "조정대상지역": [...]
          }
        }
        """
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        regions = data.get("regions")
        if not isinstance(regions, dict):
            return set(), set()

        def to_set(key: str) -> set[str]:
            raw = regions.get(key)
            if not isinstance(raw, list):
                return set()
            return {str(x).strip() for x in raw if str(x).strip()}

        return to_set("투기과열지구"), to_set("조정대상지역")

    def add_manual_fallback_data(self, fallback_json: str | Path | None = None) -> None:
        print("\n📝 fallback JSON 보완 (비어 있는 항목만)...")

        if fallback_json is not None:
            path = Path(fallback_json)
        elif os.environ.get("MOLIT_FALLBACK_JSON"):
            path = Path(os.environ["MOLIT_FALLBACK_JSON"])
        else:
            path = DEFAULT_FALLBACK_JSON

        if not path.is_file():
            print(f"   ⚠️ fallback JSON 파일 없음: {path.resolve()} — 병합 생략")
            return

        try:
            fallback_speculation, fallback_adjustment = self._load_fallback_regions_from_json(path)
        except (json.JSONDecodeError, OSError) as e:
            print(f"   ⚠️ fallback JSON 읽기 실패 ({path}): {e}")
            return

        print(f"   · fallback 소스: {path.resolve()}")

        hot: Set[str] = self.regulation_data["투기과열지구"]  # type: ignore[assignment]
        adj: Set[str] = self.regulation_data["조정대상지역"]  # type: ignore[assignment]

        if len(hot) == 0:
            print("   ⚠️ 투기과열지구 크롤 결과 없음 — fallback 병합")
            hot.update(fallback_speculation)
        if len(adj) == 0:
            print("   ⚠️ 조정대상지역 크롤 결과 없음 — fallback 병합")
            adj.update(fallback_adjustment)
        adj.difference_update(hot)

    def save_to_json(
        self,
        output_file: str | None = None,
        *,
        run_crawl: bool = True,
        fallback_json: str | Path | None = None,
    ) -> str:
        """run_crawl=True 이면 크롤부터 수행. False면 현재 regulation_data에 fallback만 보완 후 저장."""

        if output_file is None:
            output_file = str(
                Path(__file__).resolve().parent.parent / "rules/crawled" / "regulation_areas.json"
            )

        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if run_crawl:
            self.crawl_regulation_areas()
        self.add_manual_fallback_data(fallback_json=fallback_json)
        result = self._to_result_dict()

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n💾 {out_path.resolve()} 저장 완료")
        return str(out_path.resolve())
