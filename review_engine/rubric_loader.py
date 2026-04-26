from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_rubric(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Rubric not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        rubric = yaml.safe_load(file)

    if "project_name" not in rubric:
        raise ValueError("Rubric must include project_name.")

    if "sections" not in rubric:
        raise ValueError("Rubric must include sections.")

    return rubric
