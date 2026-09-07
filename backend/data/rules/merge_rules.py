"""
``rules/manual`` + ``rules/crawled`` JSON 을 비교·병합해 ``rules/merge`` 에 저장한다.

- ``last_updated`` 를 파싱해 최신 파일을 우선(base)으로 선택
- ``regulation_areas.json``: base 기준 + 다른 쪽을 합집합 보완(중복 제거·정렬)
- ``dti_dsr_rules.json``: base 기준 + 다른 쪽 ``dti_rules/dsr_rules/notes`` 깊은 병합
- ``last_updated`` 파싱 실패 시 manual 우선
- 둘 중 하나만 있으면 해당 파일 그대로 사용
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_RULES_DIR = Path(__file__).resolve().parent
_MANUAL_DIR = _RULES_DIR / "manual"
_CRAWLED_DIR = _RULES_DIR / "crawled"
_MERGE_DIR = _RULES_DIR / "merge"
_HISTORY_DIR = _RULES_DIR / "history"
_UPDATE_LOG_PATH = _HISTORY_DIR / "update_log.json"

_MANUAL_ONLY_COPY = (
    "ltv_rules.json",
    "policy_loans.json",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _kst_datetime_minute_str() -> str:
    """한국 시각 기준 ``YYYY-MM-DD HH:MM`` (년월일 시분)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _kst_date_str() -> str:
    """병합 파일 생성일(한국 달력 기준 YYYY-MM-DD)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()


def _stamp_merge_date(out: dict[str, Any]) -> None:
    """merge 산출물에 ``date``(만든 날짜) 및 ``merge_meta.date`` 기록."""
    d = _kst_date_str()
    out["date"] = d
    mm = out.get("merge_meta")
    if not isinstance(mm, dict):
        mm = {}
        out["merge_meta"] = mm
    mm["date"] = d


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else None


def _write_json(path: Path, data: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(path.resolve())


def _deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """같은 키는 overlay 가 덮어쓴다. 둘 다 dict 이면 재귀."""
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge_dict(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _parse_last_updated(value: Any) -> datetime | None:
    """``last_updated`` 문자열을 datetime으로 파싱. 실패하면 None."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        # e.g. 2026-05-11T07:31:22+00:00 / 2026-05-11T07:31:22Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    # fallback: YYYY-MM-DD
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _pick_newer_manual_crawled(
    manual: dict[str, Any],
    crawled: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    """
    last_updated 기준 최신(base)과 보완(overlay) 소스를 선택한다.
    Returns: (base, overlay, base_name, overlay_name)
    """
    m_dt = _parse_last_updated(manual.get("last_updated"))
    c_dt = _parse_last_updated(crawled.get("last_updated"))
    if m_dt and c_dt:
        if c_dt > m_dt:
            return crawled, manual, "crawled", "manual"
        return manual, crawled, "manual", "crawled"
    if c_dt and not m_dt:
        return crawled, manual, "crawled", "manual"
    # 둘 다 None 이거나 manual만 파싱 성공한 경우 manual 우선
    return manual, crawled, "manual", "crawled"


def merge_regulation_areas(
    manual: dict[str, Any],
    crawled: dict[str, Any],
) -> dict[str, Any]:
    base, overlay, base_name, overlay_name = _pick_newer_manual_crawled(manual, crawled)
    b_regions = base.get("regions")
    o_regions = overlay.get("regions")
    if not isinstance(b_regions, dict):
        b_regions = {}
    if not isinstance(o_regions, dict):
        o_regions = {}

    merged_regions: dict[str, Any] = {}
    hot: list[str] = []
    adj: list[str] = []
    for zone in ("투기과열지구", "조정대상지역"):
        a = [str(x).strip() for x in (b_regions.get(zone) or []) if str(x).strip()]
        b = [str(x).strip() for x in (o_regions.get(zone) or []) if str(x).strip()]
        if zone == "투기과열지구":
            hot = sorted(set(a + b))
        else:
            adj = sorted(set(a + b))
    hot_set = set(hot)
    adj = [x for x in adj if x not in hot_set]
    merged_regions["투기과열지구"] = hot
    merged_regions["조정대상지역"] = adj

    gen_b = b_regions.get("일반지역")
    gen_o = o_regions.get("일반지역")
    if isinstance(gen_b, list) and gen_b:
        merged_regions["일반지역"] = copy.deepcopy(gen_b)
    elif isinstance(gen_o, list) and gen_o:
        merged_regions["일반지역"] = copy.deepcopy(gen_o)
    else:
        merged_regions["일반지역"] = ["기타 모든 지역"]

    out = copy.deepcopy(base)
    out["regions"] = merged_regions
    out.pop("total_count", None)
    out["last_updated"] = _utc_now_iso()
    out["merge_meta"] = {
        "merged_at": _utc_now_iso(),
        "manual_last_updated": manual.get("last_updated"),
        "crawled_last_updated": crawled.get("last_updated"),
        "base_source": base_name,
        "overlay_source": overlay_name,
        "manual_source": manual.get("source"),
        "crawled_source": crawled.get("source"),
        "counts": {
            "투기과열지구": len(merged_regions.get("투기과열지구") or []),
            "조정대상지역": len(merged_regions.get("조정대상지역") or []),
        },
    }
    out["source"] = (
        f"{base.get('source', base_name)}; 병합({overlay.get('source', overlay_name)})"
    )
    return out


def merge_dti_dsr_rules(
    manual: dict[str, Any],
    crawled: dict[str, Any],
) -> dict[str, Any]:
    """last_updated 최신(base) + 나머지(overlay)의 dti/dsr/notes 깊은 병합."""
    base, overlay, base_name, overlay_name = _pick_newer_manual_crawled(manual, crawled)
    over = copy.deepcopy(overlay)
    crawl_meta = over.pop("crawl_meta", None)

    out = copy.deepcopy(base)
    for key in ("dti_rules", "dsr_rules", "notes"):
        if key in over and isinstance(over[key], dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out[key], over[key])
        elif key in over and isinstance(over[key], dict):
            out[key] = copy.deepcopy(over[key])

    out["last_updated"] = _utc_now_iso()
    out["source"] = (
        f"{base.get('source', base_name)}; 병합({overlay.get('source', overlay_name)})"
    )
    out["merge_meta"] = {
        "merged_at": _utc_now_iso(),
        "manual_last_updated": manual.get("last_updated"),
        "crawled_last_updated": crawled.get("last_updated"),
        "base_source": base_name,
        "overlay_source": overlay_name,
        "crawl_meta": crawl_meta,
    }
    return out


def _merge_pair(
    name: str,
    merge_fn: Any,
    manual: dict[str, Any] | None,
    crawled: dict[str, Any] | None,
) -> dict[str, Any]:
    """한 파일 쌍에 대한 병합 결과 dict."""
    if manual and crawled:
        return merge_fn(manual, crawled)
    if manual:
        out = copy.deepcopy(manual)
        out["merge_meta"] = {
            "merged_at": _utc_now_iso(),
            "note": "crawled 없음 — manual 복사",
        }
        return out
    if crawled:
        out = copy.deepcopy(crawled)
        out["merge_meta"] = {
            "merged_at": _utc_now_iso(),
            "note": "manual 없음 — crawled 만 사용",
        }
        return out
    return {}


def _append_merge_update_history(
    *,
    outputs: list[dict[str, Any]],
    all_ok: bool,
    merge_dir: str,
) -> None:
    """
    ``history/update_log.json`` 에 이번 merge 기록을 남긴다.

    - 최상단 ``updateDate``: 마지막 실행 시각(년월일 시분, KST)
    - ``updates``: 과거 실행 목록(최대 200건)
    """
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    log: dict[str, Any] = {"updateDate": "", "updates": []}
    if _UPDATE_LOG_PATH.is_file():
        try:
            with _UPDATE_LOG_PATH.open(encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, dict):
                log["updates"] = old["updates"] if isinstance(old.get("updates"), list) else []
        except (json.JSONDecodeError, OSError, TypeError):
            log["updates"] = []

    update_date = _kst_datetime_minute_str()
    entry: dict[str, Any] = {
        "updateDate": update_date,
        "all_ok": all_ok,
        "merge_dir": merge_dir,
        "files": [
            {
                "name": o.get("name"),
                "ok": o.get("ok"),
                "skipped": o.get("skipped"),
                "path": o.get("path"),
            }
            for o in outputs
        ],
    }
    log["updates"].append(entry)
    log["updates"] = log["updates"][-200:]
    log["updateDate"] = update_date

    with _UPDATE_LOG_PATH.open("w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def write_merged_rule_files(
    *,
    manual_dir: Path | None = None,
    crawled_dir: Path | None = None,
    merge_dir: Path | None = None,
) -> dict[str, Any]:
    """
    ``merge`` 디렉터리에 병합 산출물을 기록한다.

    Returns:
        ``{"outputs": [{"name", "path"|null, "ok", "error"?}], "all_ok": bool}``
    """
    manual_dir = manual_dir or _MANUAL_DIR
    crawled_dir = crawled_dir or _CRAWLED_DIR
    merge_dir = merge_dir or _MERGE_DIR

    outputs: list[dict[str, Any]] = []

    pairs: list[tuple[str, Any]] = [
        ("regulation_areas.json", merge_regulation_areas),
        ("dti_dsr_rules.json", merge_dti_dsr_rules),
    ]

    for filename, fn in pairs:
        m = _read_json(manual_dir / filename)
        c = _read_json(crawled_dir / filename)
        rec: dict[str, Any] = {"name": filename, "ok": False, "path": None}
        try:
            if not m and not c:
                rec["error"] = "manual·crawled 모두 없음"
                outputs.append(rec)
                continue
            merged = _merge_pair(filename, fn, m, c)
            if not merged:
                rec["error"] = "병합 결과 비어 있음"
                outputs.append(rec)
                continue
            _stamp_merge_date(merged)
            path = _write_json(merge_dir / filename, merged)
            rec["ok"] = True
            rec["path"] = path
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        outputs.append(rec)

    for filename in _MANUAL_ONLY_COPY:
        rec: dict[str, Any] = {"name": filename, "ok": False, "path": None}
        try:
            m = _read_json(manual_dir / filename)
            if not m:
                rec["ok"] = True
                rec["skipped"] = True
                rec["reason"] = "manual 파일 없음 — 생략"
                outputs.append(rec)
                continue
            out = copy.deepcopy(m)
            out["merge_meta"] = {
                "merged_at": _utc_now_iso(),
                "note": "crawled 없음 — manual 복사(규칙 엔진 보조 파일)",
            }
            _stamp_merge_date(out)
            path = _write_json(merge_dir / filename, out)
            rec["ok"] = True
            rec["path"] = path
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        outputs.append(rec)

    all_ok = all(o.get("ok") for o in outputs)
    merge_dir_str = str(merge_dir.resolve())
    try:
        _append_merge_update_history(
            outputs=outputs,
            all_ok=all_ok,
            merge_dir=merge_dir_str,
        )
    except Exception as e:
        logger.warning("history/update_log.json 기록 실패: %s", e)
    return {"outputs": outputs, "all_ok": all_ok, "merge_dir": merge_dir_str}
