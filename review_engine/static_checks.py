from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from review_engine.utils import (
    find_file_case_insensitive,
    list_all_files,
    normalize_text,
    read_text_safely,
)


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _text_snippets(path: Path, root: Path, keywords: list[str], max_snippets: int = 5) -> list[dict[str, Any]]:
    snippets = []
    keywords = [str(keyword) for keyword in keywords]
    lines = read_text_safely(path).splitlines()

    for line_number, line in enumerate(lines, start=1):
        normalized_line = line.lower()
        matched_keywords = [keyword for keyword in keywords if keyword.lower() in normalized_line]
        if not matched_keywords:
            continue

        snippets.append(
            {
                "file": _relative(path, root),
                "line": line_number,
                "matched_keywords": matched_keywords,
                "quote": line.strip()[:200],
            }
        )

        if len(snippets) >= max_snippets:
            break

    return snippets


def check_file_exists(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    path = check["path"]
    found_path = find_file_case_insensitive(root, path)

    passed = found_path is not None and found_path.is_file()
    return {
        "passed": passed,
        "message": f"File {'found' if passed else 'not found'}: {path}",
        "evidence": {"file": _relative(found_path, root)} if passed else None,
    }


def check_folder_exists(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    path = check["path"]
    found_path = find_file_case_insensitive(root, path)

    passed = found_path is not None and found_path.is_dir()
    return {
        "passed": passed,
        "message": f"Folder {'found' if passed else 'not found'}: {path}",
        "evidence": {"folder": _relative(found_path, root)} if passed else None,
    }


def check_glob_exists(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    pattern = check["pattern"]
    matches = sorted(str(path.relative_to(root)) for path in root.glob(pattern))

    passed = len(matches) > 0
    return {
        "passed": passed,
        "message": f"Glob pattern {'matched' if passed else 'did not match'}: {pattern}",
        "evidence": {"matches": matches[:20], "total_matches": len(matches)},
    }


def check_text_contains_any(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    path = check["path"]
    keywords = [str(keyword) for keyword in check.get("keywords", [])]

    found_path = find_file_case_insensitive(root, path)
    if found_path is None or not found_path.is_file():
        return {
            "passed": False,
            "message": f"Cannot search text because file was not found: {path}",
            "evidence": None,
        }

    text = normalize_text(read_text_safely(found_path))
    matched = [keyword for keyword in keywords if keyword.lower() in text]
    snippets = _text_snippets(found_path, root, matched)

    return {
        "passed": len(matched) > 0,
        "message": (
            f"Found at least one keyword in {path}: {matched}"
            if matched
            else f"No expected keywords found in {path}: {keywords}"
        ),
        "evidence": {
            "file": _relative(found_path, root),
            "matched": matched,
            "missing": [keyword for keyword in keywords if keyword not in matched],
            "snippets": snippets,
        },
    }


def check_text_contains_all(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    path = check["path"]
    keywords = [str(keyword) for keyword in check.get("keywords", [])]

    found_path = find_file_case_insensitive(root, path)
    if found_path is None or not found_path.is_file():
        return {
            "passed": False,
            "message": f"Cannot search text because file was not found: {path}",
            "evidence": None,
        }

    text = normalize_text(read_text_safely(found_path))
    matched = [keyword for keyword in keywords if keyword.lower() in text]
    missing = [keyword for keyword in keywords if keyword.lower() not in text]
    snippets = _text_snippets(found_path, root, matched)

    return {
        "passed": len(missing) == 0,
        "message": (
            f"All expected keywords found in {path}."
            if not missing
            else f"Missing expected keywords in {path}: {missing}"
        ),
        "evidence": {
            "file": _relative(found_path, root),
            "matched": matched,
            "missing": missing,
            "snippets": snippets,
        },
    }


def check_package_json_has_dependency(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    package_path = find_file_case_insensitive(root, "package.json")

    if package_path is None:
        return {
            "passed": False,
            "message": "package.json not found.",
            "evidence": None,
        }

    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "passed": False,
            "message": f"Could not parse package.json: {exc}",
            "evidence": None,
        }

    dependency_names = check.get("dependencies", [])
    dependencies = package.get("dependencies", {})
    dev_dependencies = package.get("devDependencies", {})
    all_dependencies = {**dependencies, **dev_dependencies}

    matched = [name for name in dependency_names if name in all_dependencies]
    missing = [name for name in dependency_names if name not in all_dependencies]

    pass_mode = check.get("mode", "any")
    passed = len(matched) > 0 if pass_mode == "any" else len(missing) == 0

    return {
        "passed": passed,
        "message": (
            f"Matched package dependencies: {matched}"
            if matched
            else f"None of the expected dependencies were found: {dependency_names}"
        ),
        "evidence": {
            "file": _relative(package_path, root),
            "matched": matched,
            "missing": missing,
        },
    }


def check_package_json_has_script(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    package_path = find_file_case_insensitive(root, "package.json")

    if package_path is None:
        return {
            "passed": False,
            "message": "package.json not found.",
            "evidence": None,
        }

    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "passed": False,
            "message": f"Could not parse package.json: {exc}",
            "evidence": None,
        }

    scripts = package.get("scripts", {})
    expected_scripts = check.get("scripts", [])

    matched = [script for script in expected_scripts if script in scripts]
    missing = [script for script in expected_scripts if script not in scripts]

    pass_mode = check.get("mode", "any")
    passed = len(matched) > 0 if pass_mode == "any" else len(missing) == 0

    return {
        "passed": passed,
        "message": (
            f"Matched package scripts: {matched}"
            if matched
            else f"None of the expected scripts were found: {expected_scripts}"
        ),
        "evidence": {
            "file": _relative(package_path, root),
            "matched": matched,
            "missing": missing,
            "available_scripts": list(scripts.keys()),
        },
    }


def check_file_list_contains_any(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    keywords = [str(keyword).lower() for keyword in check.get("keywords", [])]
    files = list_all_files(root)

    matched = [
        filename for filename in files
        if any(keyword in filename.lower() for keyword in keywords)
    ]

    return {
        "passed": len(matched) > 0,
        "message": (
            f"Found files matching expected keywords: {matched[:10]}"
            if matched
            else f"No files matched expected keywords: {keywords}"
        ),
        "evidence": {"matches": matched[:20], "total_matches": len(matched)},
    }


def check_file_list_contains_all(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    keywords = [str(keyword).lower() for keyword in check.get("keywords", [])]
    files = list_all_files(root)

    matches_by_keyword = {
        keyword: [
            filename for filename in files
            if keyword in filename.lower()
        ][:10]
        for keyword in keywords
    }
    missing = [
        keyword for keyword, matches in matches_by_keyword.items()
        if not matches
    ]

    return {
        "passed": len(missing) == 0,
        "message": (
            "Found files for all expected keywords."
            if not missing
            else f"Missing files matching expected keywords: {missing}"
        ),
        "evidence": {
            "matched": [keyword for keyword in keywords if keyword not in missing],
            "missing": missing,
            "matches_by_keyword": matches_by_keyword,
        },
    }


def check_run_command(root: Path, check: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    command = check.get("command", [])
    if isinstance(command, str):
        return {
            "passed": False,
            "message": "Runtime command must be a list of arguments, not a shell string.",
            "evidence": {"command": command},
            "review_method": "runtime_execution",
            "runtime_status": "not_run",
        }

    if not context.get("enable_runtime_checks", False):
        return {
            "passed": False,
            "message": "Runtime check skipped. Re-run with --enable-runtime-checks to execute it.",
            "evidence": {"command": command},
            "review_method": "runtime_execution",
            "runtime_status": "skipped",
        }

    if not command:
        return {
            "passed": False,
            "message": "Runtime command is empty.",
            "evidence": {"command": command},
            "review_method": "runtime_execution",
            "runtime_status": "not_run",
        }

    workdir = root
    if check.get("cwd"):
        requested_workdir = (root / str(check["cwd"])).resolve()
        if not requested_workdir.is_relative_to(root.resolve()):
            return {
                "passed": False,
                "message": f"Runtime cwd is outside the extracted project: {check['cwd']}",
                "evidence": {"command": command, "cwd": check["cwd"]},
                "review_method": "runtime_execution",
                "runtime_status": "not_run",
            }
        workdir = requested_workdir

    timeout_seconds = int(check.get("timeout_seconds", 120))
    expected_exit_code = int(check.get("expected_exit_code", 0))
    max_output_chars = int(check.get("max_output_chars", 4000))

    try:
        completed = subprocess.run(
            [str(part) for part in command],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        return {
            "passed": False,
            "message": f"Runtime command timed out after {timeout_seconds} seconds.",
            "evidence": {
                "command": command,
                "cwd": _relative(workdir, root) if workdir != root else ".",
                "timeout_seconds": timeout_seconds,
                "stdout": stdout[-max_output_chars:],
                "stderr": stderr[-max_output_chars:],
            },
            "review_method": "runtime_execution",
            "runtime_status": "timeout",
        }
    except FileNotFoundError as exc:
        return {
            "passed": False,
            "message": f"Runtime command could not start: {exc}",
            "evidence": {"command": command},
            "review_method": "runtime_execution",
            "runtime_status": "failed_to_start",
        }

    passed = completed.returncode == expected_exit_code
    return {
        "passed": passed,
        "message": (
            f"Runtime command exited with expected code {expected_exit_code}."
            if passed
            else f"Runtime command exited with code {completed.returncode}; expected {expected_exit_code}."
        ),
        "evidence": {
            "command": command,
            "cwd": _relative(workdir, root) if workdir != root else ".",
            "exit_code": completed.returncode,
            "expected_exit_code": expected_exit_code,
            "stdout": completed.stdout[-max_output_chars:],
            "stderr": completed.stderr[-max_output_chars:],
        },
        "review_method": "runtime_execution",
        "runtime_status": "passed" if passed else "failed",
    }


CHECKS = {
    "file_exists": check_file_exists,
    "folder_exists": check_folder_exists,
    "glob_exists": check_glob_exists,
    "text_contains_any": check_text_contains_any,
    "text_contains_all": check_text_contains_all,
    "package_json_has_dependency": check_package_json_has_dependency,
    "package_json_has_script": check_package_json_has_script,
    "file_list_contains_any": check_file_list_contains_any,
    "file_list_contains_all": check_file_list_contains_all,
    "run_command": check_run_command,
}


def run_static_check(
    root: Path,
    check: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    check_type = check["type"]

    if check_type not in CHECKS:
        return {
            "passed": False,
            "message": f"Unsupported check type: {check_type}",
            "evidence": None,
        }

    if check_type == "run_command":
        result = CHECKS[check_type](root, check, context)
    else:
        result = CHECKS[check_type](root, check)

    result["id"] = check.get("id", check_type)
    result["type"] = check_type
    result["description"] = check.get("description", "")
    result.setdefault("review_method", "static_inspection")
    result.setdefault("runtime_status", "not_run")
    return result
