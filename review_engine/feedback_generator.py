from __future__ import annotations

import json
from typing import Any


def _status_emoji(status: str) -> str:
    return "✅" if status == "Passes" else "❌"


def _method_label(check: dict[str, Any]) -> str:
    review_method = check.get("review_method", "static_inspection")
    runtime_status = check.get("runtime_status", "not_run")

    if review_method == "static_inspection" and runtime_status == "not_run":
        return "Static inspection; runtime not run"

    return f"{review_method}; runtime: {runtime_status}"


def _format_evidence(evidence: Any) -> list[str]:
    if evidence is None:
        return ["  - Evidence: none found"]

    if isinstance(evidence, dict):
        lines = []
        file_name = evidence.get("file") or evidence.get("folder")
        if file_name:
            lines.append(f"  - Evidence location: `{file_name}`")

        if "matches" in evidence:
            matches = evidence.get("matches") or []
            formatted = ", ".join(f"`{match}`" for match in matches[:10]) or "none"
            lines.append(f"  - Matches: {formatted}")
            if "total_matches" in evidence:
                lines.append(f"  - Total matches: {evidence['total_matches']}")

        if "matched" in evidence:
            matched = evidence.get("matched") or []
            formatted = ", ".join(f"`{item}`" for item in matched) or "none"
            lines.append(f"  - Matched values: {formatted}")

        if "missing" in evidence:
            missing = evidence.get("missing") or []
            formatted = ", ".join(f"`{item}`" for item in missing) or "none"
            lines.append(f"  - Missing values: {formatted}")

        if "available_scripts" in evidence:
            scripts = evidence.get("available_scripts") or []
            formatted = ", ".join(f"`{script}`" for script in scripts) or "none"
            lines.append(f"  - Available scripts: {formatted}")

        if "matches_by_keyword" in evidence:
            for keyword, matches in evidence.get("matches_by_keyword", {}).items():
                formatted = ", ".join(f"`{match}`" for match in matches[:5]) or "none"
                lines.append(f"  - `{keyword}` files: {formatted}")

        snippets = evidence.get("snippets") or []
        for snippet in snippets[:3]:
            lines.append(
                "  - Quote: "
                f"`{snippet.get('file')}:{snippet.get('line')}` "
                f"“{snippet.get('quote', '')}”"
            )

        if lines:
            return lines

    return ["  - Evidence: " + json.dumps(evidence, ensure_ascii=False)]


def _format_check_result(check: dict[str, Any]) -> str:
    symbol = "✅" if check["passed"] else "❌"
    description = check.get("description") or check.get("id") or check.get("type")
    message = check.get("message", "")

    lines = [
        f"- {symbol} **{description}** — {message}",
        f"  - Review method: {_method_label(check)}",
    ]
    lines.extend(_format_evidence(check.get("evidence")))
    return "\n".join(lines)


def generate_feedback_markdown(
    project_name: str,
    detected: dict[str, Any],
    evaluation: dict[str, Any],
) -> str:
    summary = evaluation["summary"]

    lines = [
        "# Project Review Feedback",
        "",
        "## Review Summary",
        "",
        f"Detected project: **{detected.get('detected_project', 'Unknown')}**",
        f"Detection confidence: **{detected.get('confidence', 0):.2f}**",
        "",
        f"Rubric project: **{project_name}**",
        "",
        f"Sections passed: **{summary['passed_sections']} / {summary['total_sections']}**",
        f"Review method: **{summary.get('review_method', 'static_inspection')}**",
        f"Runtime status: **{summary.get('runtime_status', 'not_run')}**",
        "",
    ]

    if detected.get("evidence"):
        lines.extend(
            [
                "### Project Detection Evidence",
                "",
            ]
        )
        for item in detected["evidence"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(
        [
            "## Important Note",
            "",
            "This review was generated from static evidence only. Runtime commands such as installation, tests, build, database migrations, or server startup were not run in this MVP unless explicitly added later.",
            "",
            "Treat each pass/fail result as an evidence-based draft: it means the expected files, text, dependencies, or patterns were observed. It does not prove the project works at runtime.",
            "",
        ]
    )

    for section in evaluation["sections"]:
        status = section["status"]
        lines.extend(
            [
                "---",
                "",
                f"## {_status_emoji(status)} {section['title']}",
                "",
                f"**Requirement:** {section['requirement']}",
                "",
                f"**Status:** {status}",
                "",
                f"**Review method:** {section.get('review_method', 'static_inspection')}",
                "",
                f"**Runtime status:** {section.get('runtime_status', 'not_run')}",
                "",
                "### Evidence Checked",
                "",
            ]
        )

        for check in section["checks"]:
            lines.append(_format_check_result(check))

        lines.append("")

        feedback = section["pass_feedback"] if status == "Passes" else section["fail_feedback"]
        if feedback:
            lines.extend(
                [
                    "### Feedback",
                    "",
                    feedback.strip(),
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "### Feedback",
                    "",
                    (
                        "This section appears to meet the required checks."
                        if status == "Passes"
                        else "This section needs revision based on the missing checks above."
                    ),
                    "",
                ]
            )

    lines.extend(
        [
            "---",
            "",
            "## Final Reviewer Reminder",
            "",
            "Please manually verify the important claims before submitting the review. The agent is designed to assist with evidence gathering and feedback drafting, not to replace your final judgment.",
            "",
        ]
    )

    return "\n".join(lines)
