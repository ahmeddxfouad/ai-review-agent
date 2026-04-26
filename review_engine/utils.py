from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_text_safely(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def normalize_text(text: str) -> str:
    return text.lower().replace("\r\n", "\n").replace("\r", "\n")


def find_file_case_insensitive(root: Path, relative_path: str) -> Path | None:
    parts = Path(relative_path).parts
    current = root

    for part in parts:
        if not current.exists() or not current.is_dir():
            return None

        matches = [p for p in current.iterdir() if p.name.lower() == part.lower()]
        if not matches:
            return None
        current = matches[0]

    return current


def list_all_files(root: Path) -> list[str]:
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
    )
