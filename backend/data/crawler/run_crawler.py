"""
`molit_policy_crawler` · `dti_dsr_rules_crawler` ·
`ltv_rules_crawler` · `policy_loans_crawler` 실행 진입점.

backend 디렉터리에서:

    python data/crawler/run_crawler.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _step(name: str, fn: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "ok": False}
    try:
        result = fn()
        out["ok"] = True
        if result is not None:
            out["result"] = result
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()
    return out


def run_molit_policy_crawler(
    *,
    output_file: str | Path | None = None,
    fallback_json: str | Path | None = None,
) -> str:
    """``molit_policy_crawler.MOLITRegulationCrawler.save_to_json`` — 규제지역 JSON."""
    from data.crawler.molit_policy_crawler import MOLITRegulationCrawler

    c = MOLITRegulationCrawler()
    return c.save_to_json(
        str(output_file) if output_file is not None else None,
        fallback_json=fallback_json,
    )


def run_dti_dsr_rules_crawler(
    *,
    output_file: str | Path | None = None,
    baseline_json: str | Path | None = None,
) -> str:
    """``dti_dsr_rules_crawler.DtiDsrRulesCrawler.save_to_json`` — DTI/DSR 규칙 JSON."""
    from data.crawler.dti_dsr_rules_crawler import DtiDsrRulesCrawler

    c = DtiDsrRulesCrawler()
    return c.save_to_json(
        output_file,
        baseline_json=baseline_json,
    )


def run_ltv_rules_crawler(
    *,
    output_file: str | Path | None = None,
    baseline_json: str | Path | None = None,
) -> str:
    """``ltv_rules_crawler.LtvRulesCrawler.save_to_json`` — LTV 규칙 JSON."""
    from data.crawler.ltv_rules_crawler import LtvRulesCrawler

    c = LtvRulesCrawler()
    return c.save_to_json(
        output_file,
        baseline_json=baseline_json,
    )


def run_policy_loans_crawler(
    *,
    output_file: str | Path | None = None,
    baseline_json: str | Path | None = None,
) -> str:
    """``policy_loans_crawler.PolicyLoansCrawler.save_to_json`` — 정책대출 규칙 JSON."""
    from data.crawler.policy_loans_crawler import PolicyLoansCrawler

    c = PolicyLoansCrawler()
    return c.save_to_json(
        output_file,
        baseline_json=baseline_json,
    )


def run_merge_rules() -> dict[str, Any]:
    """``rules/manual`` + ``rules/crawled`` → ``rules/merge`` 병합."""
    from data.rules.merge_rules import write_merged_rule_files

    return write_merged_rule_files()


def run_all_crawlers(
    *,
    run_molit_regulation: bool = True,
    run_dti_dsr: bool = True,
    run_ltv_rules: bool = True,
    run_policy_loans: bool = True,
    run_merge: bool = True,
) -> dict[str, Any]:
    """
    두 크롤러 모듈의 저장 파이프라인을 순서대로 실행한 뒤,
    선택적으로 ``rules/manual`` 과 ``rules/crawled`` 를 병합해 ``rules/merge`` 에 기록한다.

    Returns:
        ``{"steps": [...], "all_ok": bool, "merge"?: {...}}``
    """
    steps: list[dict[str, Any]] = []

    if run_molit_regulation:
        steps.append(
            _step("molit_policy_crawler", lambda: run_molit_policy_crawler())
        )

    if run_dti_dsr:
        steps.append(
            _step("dti_dsr_rules_crawler", lambda: run_dti_dsr_rules_crawler())
        )

    if run_ltv_rules:
        steps.append(
            _step("ltv_rules_crawler", lambda: run_ltv_rules_crawler())
        )

    if run_policy_loans:
        steps.append(
            _step("policy_loans_crawler", lambda: run_policy_loans_crawler())
        )

    crawl_ok = all(s.get("ok") for s in steps) if steps else True
    merge_out: dict[str, Any] | None = None

    if run_merge:
        merge_out = _step("merge_rules", run_merge_rules)
        steps.append(merge_out)

    all_ok = all(s.get("ok") for s in steps) if steps else True
    out: dict[str, Any] = {"steps": steps, "all_ok": all_ok, "crawl_all_ok": crawl_ok}
    if merge_out is not None:
        out["merge"] = {
            "all_ok": merge_out.get("ok"),
            "result": merge_out.get("result"),
            "error": merge_out.get("error"),
        }
    return out


def main() -> None:
    summary = run_all_crawlers()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary.get("all_ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
