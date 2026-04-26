from __future__ import annotations

import json
import re
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


def _code_files(root: Path, patterns: list[str] | None = None) -> list[Path]:
    patterns = patterns or [
        "**/*.py",
        "**/*.js",
        "**/*.jsx",
        "**/*.ts",
        "**/*.tsx",
        "**/*.sql",
        "**/*.html",
        "**/*.css",
    ]
    ignored_parts = {"node_modules", ".git", ".venv", "venv", "__pycache__"}
    files: list[Path] = []

    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            if any(part in ignored_parts for part in path.parts):
                continue
            files.append(path)

    return sorted(set(files))


def _pattern_snippets(
    path: Path,
    root: Path,
    patterns: list[str],
    *,
    regex: bool = False,
    max_snippets: int = 5,
) -> list[dict[str, Any]]:
    snippets = []
    lines = read_text_safely(path).splitlines()

    for line_number, line in enumerate(lines, start=1):
        matched_patterns = []
        for pattern in patterns:
            if regex:
                if re.search(pattern, line, flags=re.IGNORECASE):
                    matched_patterns.append(pattern)
            elif pattern.lower() in line.lower():
                matched_patterns.append(pattern)

        if not matched_patterns:
            continue

        snippets.append(
            {
                "file": _relative(path, root),
                "line": line_number,
                "matched_patterns": matched_patterns,
                "quote": line.strip()[:200],
            }
        )

        if len(snippets) >= max_snippets:
            break

    return snippets


def _json_key_exists(data: Any, key_path: str) -> bool:
    current = data
    for part in key_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return False
    return True


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


def check_code_contains_pattern(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    patterns = [str(pattern) for pattern in check.get("patterns", [])]
    mode = check.get("mode", "any")
    use_regex = bool(check.get("regex", False))
    file_patterns = check.get("file_patterns")
    files = _code_files(root, file_patterns)

    matches_by_pattern: dict[str, list[str]] = {pattern: [] for pattern in patterns}
    snippets = []

    for path in files:
        text = read_text_safely(path)
        for pattern in patterns:
            matched = (
                re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None
                if use_regex
                else pattern.lower() in text.lower()
            )
            if matched:
                matches_by_pattern[pattern].append(_relative(path, root))

        snippets.extend(
            _pattern_snippets(
                path,
                root,
                patterns,
                regex=use_regex,
                max_snippets=max(0, 5 - len(snippets)),
            )
        )
        if len(snippets) >= 5:
            snippets = snippets[:5]

    matched = [
        pattern for pattern, locations in matches_by_pattern.items()
        if locations
    ]
    missing = [
        pattern for pattern, locations in matches_by_pattern.items()
        if not locations
    ]
    passed = len(matched) > 0 if mode == "any" else len(missing) == 0

    return {
        "passed": passed,
        "message": (
            f"Matched code patterns: {matched}"
            if matched
            else f"No expected code patterns found: {patterns}"
        ),
        "evidence": {
            "matched": matched,
            "missing": missing,
            "matches_by_pattern": {
                pattern: locations[:10]
                for pattern, locations in matches_by_pattern.items()
            },
            "snippets": snippets,
        },
    }


def check_code_contains_all_patterns(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    check = {**check, "mode": "all"}
    return check_code_contains_pattern(root, check)


def check_json_file_contains_keys(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    path = check["path"]
    keys = [str(key) for key in check.get("keys", [])]
    mode = check.get("mode", "all")
    found_path = find_file_case_insensitive(root, path)

    if found_path is None or not found_path.is_file():
        return {
            "passed": False,
            "message": f"JSON file not found: {path}",
            "evidence": None,
        }

    try:
        data = json.loads(found_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "passed": False,
            "message": f"Could not parse JSON file {path}: {exc}",
            "evidence": {"file": _relative(found_path, root)},
        }

    matched = [key for key in keys if _json_key_exists(data, key)]
    missing = [key for key in keys if key not in matched]
    passed = len(matched) > 0 if mode == "any" else len(missing) == 0

    return {
        "passed": passed,
        "message": (
            f"Matched JSON keys in {path}: {matched}"
            if matched
            else f"No expected JSON keys found in {path}: {keys}"
        ),
        "evidence": {
            "file": _relative(found_path, root),
            "matched": matched,
            "missing": missing,
        },
    }


def check_dependency_file_contains(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    path = check["path"]
    dependencies = [str(dependency) for dependency in check.get("dependencies", [])]
    mode = check.get("mode", "all")
    found_path = find_file_case_insensitive(root, path)

    if found_path is None or not found_path.is_file():
        return {
            "passed": False,
            "message": f"Dependency file not found: {path}",
            "evidence": None,
        }

    if found_path.name.lower() == "package.json":
        package_check = {
            "dependencies": dependencies,
            "mode": mode,
        }
        return check_package_json_has_dependency(root, package_check)

    text = normalize_text(read_text_safely(found_path))
    matched = [
        dependency for dependency in dependencies
        if re.search(rf"(^|\n)\s*{re.escape(dependency.lower())}\b", text)
    ]
    missing = [dependency for dependency in dependencies if dependency not in matched]
    passed = len(matched) > 0 if mode == "any" else len(missing) == 0

    return {
        "passed": passed,
        "message": (
            f"Matched dependencies in {path}: {matched}"
            if matched
            else f"No expected dependencies found in {path}: {dependencies}"
        ),
        "evidence": {
            "file": _relative(found_path, root),
            "matched": matched,
            "missing": missing,
            "snippets": _text_snippets(found_path, root, matched),
        },
    }


def check_gitignore_contains(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    gitignore_check = {
        "path": ".gitignore",
        "keywords": check.get("patterns", check.get("keywords", [])),
    }
    mode = check.get("mode", "all")
    if mode == "any":
        return check_text_contains_any(root, gitignore_check)
    return check_text_contains_all(root, gitignore_check)


def check_route_pattern_exists(root: Path, check: dict[str, Any]) -> dict[str, Any]:
    routes = check.get("routes", [])
    file_patterns = check.get("file_patterns") or [
        "**/*.py",
        "**/*.js",
        "**/*.jsx",
        "**/*.ts",
        "**/*.tsx",
    ]
    files = _code_files(root, file_patterns)
    matches: dict[str, list[str]] = {}
    missing = []
    snippets = []

    for route in routes:
        method = str(route.get("method", "")).lower()
        path = str(route.get("path", ""))
        route_id = f"{method.upper()} {path}"
        route_matches = []

        for file_path in files:
            text = read_text_safely(file_path)
            lowered = text.lower()
            path_patterns = {
                path.lower(),
                path.replace(":id", "<int:id>").lower(),
                path.replace(":id", "<id>").lower(),
            }
            method_patterns = {
                f".{method}(",
                f"@app.route",
                f"methods=['{method.upper()}']",
                f'methods=["{method.upper()}"]',
                f"methods=[\"{method.upper()}\"]",
            }

            if any(path_pattern in lowered for path_pattern in path_patterns) and any(
                method_pattern.lower() in lowered for method_pattern in method_patterns
            ):
                route_matches.append(_relative(file_path, root))
                snippets.extend(
                    _pattern_snippets(
                        file_path,
                        root,
                        [path, f".{method}(", "@app.route", method.upper()],
                        max_snippets=max(0, 5 - len(snippets)),
                    )
                )

        if route_matches:
            matches[route_id] = sorted(set(route_matches))[:10]
        else:
            missing.append(route_id)

    passed = not missing
    return {
        "passed": passed,
        "message": (
            "Found all expected route patterns."
            if passed
            else f"Missing expected route patterns: {missing}"
        ),
        "evidence": {
            "matched": list(matches.keys()),
            "missing": missing,
            "matches_by_pattern": matches,
            "snippets": snippets[:5],
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
    "code_contains_pattern": check_code_contains_pattern,
    "code_contains_all_patterns": check_code_contains_all_patterns,
    "json_file_contains_keys": check_json_file_contains_keys,
    "dependency_file_contains": check_dependency_file_contains,
    "gitignore_contains": check_gitignore_contains,
    "route_pattern_exists": check_route_pattern_exists,
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
