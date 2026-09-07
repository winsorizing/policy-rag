"""
``data/rules/history/update_log.json`` 및 ``rules/merge/*.json`` 의 날짜로
규칙 데이터가 '오늘 이미 갱신된 상태'인지 판별한다.

refresh 시 크롤·Chroma 재빌드를 생략할 때 사용한다. (KST 달력 기준)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_MERGE_DIR = _BACKEND_ROOT / "data" / "rules" / "merge"
_UPDATE_LOG_PATH = _BACKEND_ROOT / "data" / "rules" / "history" / "update_log.json"

_DATE_HEAD = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def kst_today_iso() -> str:
    """한국 달력 기준 오늘 ``YYYY-MM-DD``."""
    try:
        from zoneinfo import ZoneInfo

        return __import__("datetime").datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    except Exception:
        return __import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc).date().isoformat()


def _first_yyyy_mm_dd(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if len(s) < 10:
        return None
    m = _DATE_HEAD.match(s)
    return m.group(1) if m else None


def merge_dir_has_engine_files() -> bool:
    """대출 규칙 엔진에 필요한 merge 산출물이 있는지."""
    return (_MERGE_DIR / "regulation_areas.json").is_file() and (_MERGE_DIR / "dti_dsr_rules.json").is_file()


def update_log_merge_date_is_today() -> tuple[bool, str]:
    """
    ``update_log.json`` 최상단 ``updateDate`` 의 날짜 부분이 KST 오늘과 같으면 True.

    Returns:
        (is_today, human_readable_detail)
    """
    today = kst_today_iso()
    if not _UPDATE_LOG_PATH.is_file():
        return False, "update_log.json 없음"
    try:
        with _UPDATE_LOG_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"update_log 읽기 실패: {e}"
    if not isinstance(data, dict):
        return False, "update_log 형식 오류"
    ud = data.get("updateDate")
    head = _first_yyyy_mm_dd(ud)
    if not head:
        return False, "updateDate 파싱 불가"
    if head == today:
        return True, f"update_log.updateDate={ud!r} → 날짜 {head} (오늘)"
    return False, f"update_log 날짜 {head} ≠ 오늘 {today}"


def merge_json_stamp_date_is_today() -> tuple[bool, str]:
    """
    ``merge_meta.date`` 또는 최상단 ``date``(merge_rules._stamp_merge_date)가 오늘이면 True.
    update_log 가 없을 때 보조 판별용.
    """
    today = kst_today_iso()
    for name in ("regulation_areas.json", "dti_dsr_rules.json"):
        p = _MERGE_DIR / name
        if not p.is_file():
            continue
        try:
            with p.open(encoding="utf-8") as f:
                d = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(d, dict):
            continue
        mm = d.get("merge_meta")
        cand = None
        if isinstance(mm, dict):
            cand = mm.get("date")
        if cand is None:
            cand = d.get("date")
        head = _first_yyyy_mm_dd(cand)
        if head == today:
            return True, f"{name} date={cand!r} (오늘)"
    return False, "merge JSON date 스탬프가 오늘과 일치하는 파일 없음"


def should_skip_heavy_refresh() -> tuple[bool, str]:
    """
    크롤 + Chroma 전체 재빌드를 생략해도 되는지.

    조건:
    - merge 엔진용 JSON이 존재하고
    - (update_log 최상단 날짜가 오늘) 또는 (update_log 없이 merge date 스탬프가 오늘)
    """
    if not merge_dir_has_engine_files():
        return False, "merge/regulation_areas.json 또는 dti_dsr_rules.json 없음"

    ok_log, detail_log = update_log_merge_date_is_today()
    if ok_log:
        return True, detail_log

    ok_json, detail_json = merge_json_stamp_date_is_today()
    if ok_json:
        return True, detail_json + " (update_log 날짜는 오늘이 아님 — merge date 보조)"

    return False, f"{detail_log}; {detail_json}"
