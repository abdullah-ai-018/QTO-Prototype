"""Local filesystem storage helpers for uploaded blueprints, generated
page images/thumbnails, and generated reports.
"""

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings

settings = get_settings()


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in stem)[:80]


def build_stored_filename(original_filename: str) -> str:
    unique = uuid.uuid4().hex[:12]
    ext = Path(original_filename).suffix.lower()
    if not ext:
        ext = ".pdf"
    return f"{_safe_stem(original_filename)}_{unique}{ext}"


async def save_upload(upload: UploadFile, destination_dir: str | None = None) -> tuple[str, str, int]:
    """Stream an UploadFile to disk. Returns (stored_filename, absolute_path, size_bytes)."""
    directory = Path(destination_dir or settings.upload_dir)
    directory.mkdir(parents=True, exist_ok=True)

    stored_filename = build_stored_filename(upload.filename or "blueprint.pdf")
    destination = directory / stored_filename

    size = 0
    chunk_size = 1024 * 1024
    with destination.open("wb") as out_file:
        while chunk := await upload.read(chunk_size):
            size += len(chunk)
            out_file.write(chunk)
    await upload.seek(0)

    return stored_filename, str(destination.resolve()), size


def page_image_path(blueprint_id: int, page_number: int) -> str:
    directory = Path(settings.upload_dir) / f"blueprint_{blueprint_id}" / "pages"
    directory.mkdir(parents=True, exist_ok=True)
    return str((directory / f"page_{page_number:03d}.png").resolve())


def page_thumbnail_path(blueprint_id: int, page_number: int) -> str:
    directory = Path(settings.thumbnail_dir) / f"blueprint_{blueprint_id}"
    directory.mkdir(parents=True, exist_ok=True)
    return str((directory / f"page_{page_number:03d}_thumb.png").resolve())


def report_output_path(project_id: int, estimate_id: int, extension: str) -> str:
    directory = Path(settings.report_dir) / f"project_{project_id}"
    directory.mkdir(parents=True, exist_ok=True)
    return str((directory / f"estimate_{estimate_id}.{extension}").resolve())
