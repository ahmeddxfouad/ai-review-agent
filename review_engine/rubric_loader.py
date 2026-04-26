from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from review_engine.rubric_validator import validate_rubric_data


def load_rubric(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Rubric not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        rubric = yaml.safe_load(file)

    validation = validate_rubric_data(rubric)
    if not validation["valid"]:
        message = "\n".join(validation["errors"])
        raise ValueError(f"Invalid rubric: {path}\n{message}")

    if validation["warnings"]:
        # Warnings are intentionally not fatal; they are surfaced by --validate-rubric.
        pass

    return rubric
