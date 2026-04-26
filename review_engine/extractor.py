from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path


MAX_ZIP_FILES = 10_000
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024


def _is_zip_symlink(member: zipfile.ZipInfo) -> bool:
    unix_mode = member.external_attr >> 16
    return (unix_mode & 0o170000) == 0o120000


def _safe_member_path(destination: Path, member_name: str) -> Path:
    member_path = Path(member_name)

    if member_path.is_absolute() or member_path.drive:
        raise ValueError(f"Unsafe absolute zip path detected: {member_name}")

    destination_resolved = destination.resolve()
    target_resolved = (destination / member_path).resolve()

    if not target_resolved.is_relative_to(destination_resolved):
        raise ValueError(f"Unsafe zip path detected: {member_name}")

    return target_resolved


def _safe_extract(zip_file: zipfile.ZipFile, destination: Path) -> None:
    members = zip_file.infolist()
    if len(members) > MAX_ZIP_FILES:
        raise ValueError(f"Zip contains too many files: {len(members)}")

    total_uncompressed_size = sum(member.file_size for member in members)
    if total_uncompressed_size > MAX_UNCOMPRESSED_BYTES:
        raise ValueError(
            "Zip uncompressed size is too large: "
            f"{total_uncompressed_size} bytes"
        )

    for member in members:
        if _is_zip_symlink(member):
            raise ValueError(f"Unsafe zip symlink detected: {member.filename}")

        target_path = _safe_member_path(destination, member.filename)

        if member.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(member, "r") as source, target_path.open("wb") as target:
            target.write(source.read())


def extract_zip_to_review_folder(zip_path: Path) -> tuple[Path, Path]:
    review_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    review_dir = Path("reviews") / review_id
    extracted_dir = review_dir / "extracted"

    review_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    saved_zip = review_dir / "submission.zip"
    saved_zip.write_bytes(zip_path.read_bytes())

    with zipfile.ZipFile(zip_path, "r") as zip_file:
        _safe_extract(zip_file, extracted_dir)

    # If zip contains one top-level folder, use that as the root.
    children = [child for child in extracted_dir.iterdir()]
    dirs = [child for child in children if child.is_dir()]
    files = [child for child in children if child.is_file()]

    if len(dirs) == 1 and len(files) == 0:
        project_root = dirs[0]
    else:
        project_root = extracted_dir

    return review_dir, project_root
