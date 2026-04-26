from __future__ import annotations

from pathlib import Path
from typing import Any

from review_engine.static_checks import run_static_check


def _section_passed(check_results: list[dict[str, Any]], pass_rule: str) -> bool:
    if not check_results:
        return False

    if pass_rule == "all":
        return all(result["passed"] for result in check_results)

    if pass_rule == "any":
        return any(result["passed"] for result in check_results)

    raise ValueError(f"Unsupported pass_rule: {pass_rule}")


def _section_review_method(check_results: list[dict[str, Any]]) -> str:
    if any(result.get("review_method") == "runtime_execution" for result in check_results):
        return "mixed_static_and_runtime"
    return "static_inspection"


def _section_runtime_status(check_results: list[dict[str, Any]]) -> str:
    statuses = {
        result.get("runtime_status", "not_run")
        for result in check_results
    }
    runtime_statuses = statuses - {"not_run"}

    if not runtime_statuses:
        return "not_run"
    if "failed" in runtime_statuses:
        return "failed"
    if "timeout" in runtime_statuses:
        return "timeout"
    if "failed_to_start" in runtime_statuses:
        return "failed_to_start"
    if runtime_statuses == {"passed"}:
        return "passed"
    if "skipped" in runtime_statuses:
        return "skipped"
    return "mixed"


def evaluate_rubric(
    root: Path,
    rubric: dict[str, Any],
    *,
    enable_runtime_checks: bool = False,
) -> dict[str, Any]:
    section_results = []
    context = {"enable_runtime_checks": enable_runtime_checks}

    for section in rubric["sections"]:
        check_results = []

        for check in section.get("checks", []):
            check_result = run_static_check(root, check, context)
            check_results.append(check_result)

        pass_rule = section.get("pass_rule", "all")
        passed = _section_passed(check_results, pass_rule)

        section_results.append(
            {
                "id": section["id"],
                "title": section["title"],
                "requirement": section.get("requirement", ""),
                "status": "Passes" if passed else "Does Not Pass",
                "pass_rule": pass_rule,
                "review_method": _section_review_method(check_results),
                "runtime_status": _section_runtime_status(check_results),
                "checks": check_results,
                "pass_feedback": section.get("pass_feedback", ""),
                "fail_feedback": section.get("fail_feedback", ""),
            }
        )

    total = len(section_results)
    passed_count = sum(1 for section in section_results if section["status"] == "Passes")
    runtime_statuses = {
        section.get("runtime_status", "not_run")
        for section in section_results
    }
    runtime_status = "not_run"
    if runtime_statuses - {"not_run"}:
        runtime_status = "mixed"

    return {
        "summary": {
            "total_sections": total,
            "passed_sections": passed_count,
            "failed_sections": total - passed_count,
            "review_method": (
                "mixed_static_and_runtime"
                if enable_runtime_checks
                else "static_inspection"
            ),
            "runtime_status": runtime_status,
        },
        "sections": section_results,
    }
