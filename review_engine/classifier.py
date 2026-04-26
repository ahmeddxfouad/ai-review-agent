from __future__ import annotations

import json
from pathlib import Path

from review_engine.utils import find_file_case_insensitive, list_all_files, normalize_text, read_text_safely


def _read_package_json(root: Path) -> dict:
    package_path = find_file_case_insensitive(root, "package.json")
    if package_path is None:
        return {}

    try:
        return json.loads(package_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _has_file(root: Path, path: str) -> bool:
    found = find_file_case_insensitive(root, path)
    return found is not None and found.exists()


def _all_dependency_names(package: dict) -> set[str]:
    return set(package.get("dependencies", {}).keys()) | set(package.get("devDependencies", {}).keys())


def detect_project_type(root: Path) -> dict:
    files = list_all_files(root)
    file_names_lower = [file.lower() for file in files]

    package = _read_package_json(root)
    dependencies = _all_dependency_names(package)

    readme_text = ""
    readme_path = find_file_case_insensitive(root, "README.md")
    if readme_path:
        readme_text = normalize_text(read_text_safely(readme_path))

    candidates = []

    # Storefront Backend
    score = 0
    evidence = []
    if "express" in dependencies:
        score += 2
        evidence.append("package.json contains express")
    if "db-migrate" in dependencies or "db-migrate-pg" in dependencies:
        score += 2
        evidence.append("package.json contains db-migrate/db-migrate-pg")
    if any("migrations" in f for f in file_names_lower):
        score += 1
        evidence.append("migrations folder/files found")
    if any("database.json" in f for f in file_names_lower):
        score += 1
        evidence.append("database.json found")
    candidates.append(
        {
            "project": "Storefront Backend",
            "rubric_path": "rubrics/storefront_backend.yaml",
            "score": score,
            "evidence": evidence,
        }
    )

    # Angular MyStore
    score = 0
    evidence = []
    if _has_file(root, "angular.json"):
        score += 3
        evidence.append("angular.json found")
    if "@angular/core" in dependencies:
        score += 2
        evidence.append("package.json contains @angular/core")
    if any("src/app" in f.replace("\\", "/").lower() for f in file_names_lower):
        score += 1
        evidence.append("src/app files found")
    candidates.append(
        {
            "project": "Angular MyStore",
            "rubric_path": "rubrics/angular_mystore.yaml",
            "score": score,
            "evidence": evidence,
        }
    )

    # React Portfolio
    score = 0
    evidence = []
    if "react" in dependencies:
        score += 2
        evidence.append("package.json contains react")
    if any("portfolio" in f for f in file_names_lower) or "portfolio" in readme_text:
        score += 1
        evidence.append("portfolio keyword found")
    if any("src/components" in f.replace("\\", "/").lower() for f in file_names_lower):
        score += 1
        evidence.append("src/components files found")
    candidates.append(
        {
            "project": "React Portfolio",
            "rubric_path": "rubrics/react_portfolio.yaml",
            "score": score,
            "evidence": evidence,
        }
    )

    # Flask Coffee Shop
    score = 0
    evidence = []
    if any(f.endswith("app.py") for f in file_names_lower):
        score += 1
        evidence.append("app.py found")
    if any("flask" in f for f in file_names_lower) or "flask" in readme_text:
        score += 2
        evidence.append("Flask keyword found")
    if any("requirements.txt" in f for f in file_names_lower):
        score += 1
        evidence.append("requirements.txt found")
    candidates.append(
        {
            "project": "Flask Coffee Shop",
            "rubric_path": "rubrics/flask_coffee_shop.yaml",
            "score": score,
            "evidence": evidence,
        }
    )

    best = max(candidates, key=lambda item: item["score"])
    max_reasonable_score = 6
    confidence = min(best["score"] / max_reasonable_score, 1.0)

    return {
        "detected_project": best["project"] if best["score"] > 0 else "Unknown",
        "confidence": confidence,
        "rubric_path": best["rubric_path"],
        "evidence": best["evidence"],
        "all_candidates": candidates,
    }
