from __future__ import annotations

from pathlib import Path
from typing import Any

from review_engine.static_checks import run_static_check

RUNTIME_MODES = {"runtime_local", "full_review"}
LLM_MODES = {"llm_assisted", "full_review"}


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


def _allowed_in_mode(item: dict[str, Any], review_mode: str) -> bool:
    modes = item.get("modes")
    if not modes:
        return True
    return review_mode in modes


def evaluate_rubric(
    root: Path,
    rubric: dict[str, Any],
    *,
    review_mode: str = "static_only",
) -> dict[str, Any]:
    section_results = []
    context = {
        "enable_runtime_checks": review_mode in RUNTIME_MODES,
        "review_mode": review_mode,
    }

    for section in rubric["sections"]:
        if not _allowed_in_mode(section, review_mode):
            section_results.append(
                {
                    "id": section["id"],
                    "title": section["title"],
                    "requirement": section.get("requirement", ""),
                    "status": "Skipped",
                    "pass_rule": section.get("pass_rule", "all"),
                    "review_method": "not_applicable",
                    "runtime_status": "not_run",
                    "checks": [],
                    "pass_feedback": section.get("pass_feedback", ""),
                    "fail_feedback": section.get("fail_feedback", ""),
                    "skip_reason": f"Section only runs in modes: {section.get('modes')}",
                }
            )
            continue

        check_results = []

        for check in section.get("checks", []):
            if not _allowed_in_mode(check, review_mode):
                continue
            check_result = run_static_check(root, check, context)
            check_results.append(check_result)

        if not check_results:
            section_results.append(
                {
                    "id": section["id"],
                    "title": section["title"],
                    "requirement": section.get("requirement", ""),
                    "status": "Skipped",
                    "pass_rule": section.get("pass_rule", "all"),
                    "review_method": "not_applicable",
                    "runtime_status": "not_run",
                    "checks": [],
                    "pass_feedback": section.get("pass_feedback", ""),
                    "fail_feedback": section.get("fail_feedback", ""),
                    "skip_reason": "No checks apply to this review mode.",
                }
            )
            continue

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

    evaluated_sections = [
        section for section in section_results
        if section["status"] != "Skipped"
    ]
    total = len(evaluated_sections)
    passed_count = sum(1 for section in evaluated_sections if section["status"] == "Passes")
    skipped_count = len(section_results) - total
    runtime_statuses = {
        section.get("runtime_status", "not_run")
        for section in evaluated_sections
    }
    runtime_status = "not_run"
    if runtime_statuses - {"not_run"}:
        runtime_status = "mixed"

    return {
        "summary": {
            "total_sections": total,
            "passed_sections": passed_count,
            "failed_sections": total - passed_count,
            "skipped_sections": skipped_count,
            "review_method": (
                "mixed_static_and_runtime"
                if review_mode in RUNTIME_MODES
                else "static_inspection"
            ),
            "runtime_status": runtime_status,
            "review_mode": review_mode,
            "llm_status": "not_implemented" if review_mode in LLM_MODES else "not_requested",
        },
        "sections": section_results,
    }
