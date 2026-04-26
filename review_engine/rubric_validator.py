from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from review_engine.static_checks import CHECKS

VALID_PASS_RULES = {"all", "any"}
VALID_MODES = {"static_only", "runtime_local", "llm_assisted", "full_review"}

CHECK_REQUIRED_FIELDS = {
    "file_exists": {"path"},
    "folder_exists": {"path"},
    "glob_exists": {"pattern"},
    "text_contains_any": {"path", "keywords"},
    "text_contains_all": {"path", "keywords"},
    "package_json_has_dependency": {"dependencies"},
    "package_json_has_script": {"scripts"},
    "file_list_contains_any": {"keywords"},
    "file_list_contains_all": {"keywords"},
    "code_contains_pattern": {"patterns"},
    "code_contains_all_patterns": {"patterns"},
    "json_file_contains_keys": {"path", "keys"},
    "dependency_file_contains": {"path", "dependencies"},
    "gitignore_contains": {"patterns"},
    "route_pattern_exists": {"routes"},
    "run_command": {"command"},
}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _add_duplicate_errors(
    values: list[str],
    *,
    label: str,
    location: str,
    errors: list[str],
) -> None:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)

    for value in sorted(duplicates):
        errors.append(f"{location}: duplicate {label} `{value}`.")


def _validate_modes(item: dict[str, Any], location: str, errors: list[str]) -> None:
    modes = item.get("modes")
    if modes is None:
        return

    if not isinstance(modes, list) or not modes:
        errors.append(f"{location}: `modes` must be a non-empty list when provided.")
        return

    invalid_modes = [mode for mode in modes if mode not in VALID_MODES]
    if invalid_modes:
        errors.append(
            f"{location}: invalid mode(s) {invalid_modes}; expected one of {sorted(VALID_MODES)}."
        )


def _validate_runtime_command(check: dict[str, Any], location: str, errors: list[str]) -> None:
    command = check.get("command")
    if isinstance(command, str):
        errors.append(f"{location}: `command` must be a list of arguments, not a shell string.")
        return

    if not _is_non_empty_list(command):
        errors.append(f"{location}: `command` must be a non-empty list.")
        return

    if not all(isinstance(part, (str, int, float)) for part in command):
        errors.append(f"{location}: every command argument must be a string or number.")


def _validate_routes(check: dict[str, Any], location: str, errors: list[str]) -> None:
    routes = check.get("routes")
    if not _is_non_empty_list(routes):
        errors.append(f"{location}: `routes` must be a non-empty list.")
        return

    for index, route in enumerate(routes):
        route_location = f"{location}.routes[{index}]"
        if not isinstance(route, dict):
            errors.append(f"{route_location}: route must be an object.")
            continue
        if not _is_non_empty_string(route.get("method")):
            errors.append(f"{route_location}: route must include a non-empty `method`.")
        if not _is_non_empty_string(route.get("path")):
            errors.append(f"{route_location}: route must include a non-empty `path`.")


def _validate_check(
    check: Any,
    *,
    section_id: str,
    index: int,
    errors: list[str],
    warnings: list[str],
) -> str | None:
    location = f"section `{section_id}` check[{index}]"
    if not isinstance(check, dict):
        errors.append(f"{location}: check must be an object.")
        return None

    check_id = check.get("id")
    if not _is_non_empty_string(check_id):
        errors.append(f"{location}: check must include a non-empty `id`.")
        check_id = f"check_{index}"

    check_type = check.get("type")
    if not _is_non_empty_string(check_type):
        errors.append(f"{location}: check `{check_id}` must include a non-empty `type`.")
        return str(check_id)

    if check_type not in CHECKS:
        errors.append(
            f"{location}: unsupported check type `{check_type}`. "
            f"Supported types: {sorted(CHECKS)}."
        )
        return str(check_id)

    missing_fields = sorted(CHECK_REQUIRED_FIELDS.get(check_type, set()) - set(check))
    for field in missing_fields:
        errors.append(f"{location}: check `{check_id}` of type `{check_type}` is missing `{field}`.")

    _validate_modes(check, location, errors)

    mode = check.get("mode")
    if mode is not None and mode not in {"all", "any"}:
        errors.append(f"{location}: check `{check_id}` has invalid `mode` `{mode}`.")

    if check_type == "run_command":
        _validate_runtime_command(check, location, errors)

    if check_type == "route_pattern_exists":
        _validate_routes(check, location, errors)

    if not _is_non_empty_string(check.get("description")):
        warnings.append(f"{location}: check `{check_id}` has no description.")

    return str(check_id)


def validate_rubric_data(rubric: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(rubric, dict):
        return {
            "valid": False,
            "errors": ["Rubric root must be a YAML object."],
            "warnings": [],
        }

    if not _is_non_empty_string(rubric.get("project_name")):
        errors.append("Rubric must include a non-empty `project_name`.")

    sections = rubric.get("sections")
    if not _is_non_empty_list(sections):
        errors.append("Rubric must include a non-empty `sections` list.")
        sections = []

    section_ids = []
    for index, section in enumerate(sections):
        location = f"sections[{index}]"
        if not isinstance(section, dict):
            errors.append(f"{location}: section must be an object.")
            continue

        section_id = section.get("id")
        if not _is_non_empty_string(section_id):
            errors.append(f"{location}: section must include a non-empty `id`.")
            section_id = f"section_{index}"
        section_id = str(section_id)
        section_ids.append(section_id)
        section_location = f"section `{section_id}`"

        if not _is_non_empty_string(section.get("title")):
            errors.append(f"{section_location}: missing non-empty `title`.")

        if not _is_non_empty_string(section.get("requirement")):
            errors.append(f"{section_location}: missing non-empty `requirement`.")

        pass_rule = section.get("pass_rule", "all")
        if pass_rule not in VALID_PASS_RULES:
            errors.append(
                f"{section_location}: invalid `pass_rule` `{pass_rule}`; "
                f"expected one of {sorted(VALID_PASS_RULES)}."
            )

        _validate_modes(section, section_location, errors)

        checks = section.get("checks", [])
        if not _is_non_empty_list(checks):
            errors.append(f"{section_location}: must include a non-empty `checks` list.")
            checks = []

        check_ids = []
        for check_index, check in enumerate(checks):
            check_id = _validate_check(
                check,
                section_id=section_id,
                index=check_index,
                errors=errors,
                warnings=warnings,
            )
            if check_id:
                check_ids.append(check_id)

        _add_duplicate_errors(
            check_ids,
            label="check id",
            location=section_location,
            errors=errors,
        )

        if not _is_non_empty_string(section.get("pass_feedback")):
            warnings.append(f"{section_location}: missing `pass_feedback`.")

        if not _is_non_empty_string(section.get("fail_feedback")):
            warnings.append(f"{section_location}: missing `fail_feedback`.")

    _add_duplicate_errors(
        section_ids,
        label="section id",
        location="rubric",
        errors=errors,
    )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def validate_rubric_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "valid": False,
            "errors": [f"Rubric file not found: {path}"],
            "warnings": [],
        }

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            rubric = yaml.safe_load(file)
    except Exception as exc:
        return {
            "valid": False,
            "errors": [f"Could not parse rubric YAML: {exc}"],
            "warnings": [],
        }

    return validate_rubric_data(rubric)
