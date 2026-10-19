from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ALLOWED_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".dng",
        ".nef",
        ".cr2",
        ".cr3",
        ".arw",
        ".orf",
        ".rw2",
        ".raf",
        ".pef",
        ".srw",
    }
)
RAWS = ALLOWED_EXTENSIONS - {".jpg", ".jpeg", ".png"}
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
REFERENCE_RE = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{2,5}$")


class LemioPhotoError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SourcePhoto:
    path: str
    original_filename: str
    mime_type: str
    size: int
    sha256: str
    extension: str


@dataclass(frozen=True, slots=True)
class WorkingPhoto:
    path: str
    filename: str
    mime_type: str
    size: int
    width: int
    height: int
    sha256: str


@dataclass(frozen=True, slots=True)
class DevelopParameters:
    values: dict[str, Any]
    analysis: str = ""


@dataclass(frozen=True, slots=True)
class ProcessedPhoto:
    path: str
    filename: str
    mime_type: str
    size: int
    width: int
    height: int
    sha256: str


@dataclass(frozen=True, slots=True)
class FinalPhoto:
    path: str
    filename: str
    mime_type: str
    size: int
    width: int
    height: int
    sha256: str


def max_upload_bytes() -> int:
    return _positive_mb("PHOTO_PIPELINE_MAX_UPLOAD_MB", 100)


def max_response_bytes() -> int:
    return _positive_mb("PHOTO_PIPELINE_MAX_RESPONSE_MB", 100)


def _positive_mb(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise LemioPhotoError(f"{name} must be an integer number of MB") from exc
    if value < 1:
        raise LemioPhotoError(f"{name} must be at least 1 MB")
    return value * 1024 * 1024


def extension_for(filename: str) -> str:
    if not filename or "\x00" in filename:
        raise LemioPhotoError("A valid filename is required")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise LemioPhotoError(f"Unsupported photo extension: {ext or '(none)'}")
    return ext


def validate_signature(path: Path, extension: str) -> None:
    if extension in RAWS:
        return
    with path.open("rb") as handle:
        header = handle.read(8)
    if extension in {".jpg", ".jpeg"} and not header.startswith(JPEG_MAGIC):
        raise LemioPhotoError("File content is not a JPEG")
    if extension == ".png" and header != PNG_MAGIC:
        raise LemioPhotoError("File content is not a PNG")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_child(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute() or "\x00" in relative:
        raise LemioPhotoError("Invalid file reference")
    root = root.resolve()
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise LemioPhotoError("File reference escapes the managed directory") from exc
    if candidate.exists() and candidate.is_symlink():
        raise LemioPhotoError("Symbolic links are not allowed")
    return candidate


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def save_metadata(path: Path, value: SourcePhoto | WorkingPhoto) -> None:
    atomic_json(path, asdict(value))


def load_source(upload_root: Path, reference: str) -> SourcePhoto:
    if not REFERENCE_RE.fullmatch(reference):
        raise LemioPhotoError("Invalid upload reference; upload the photo again")
    photo_path = safe_child(upload_root, reference)
    metadata_path = safe_child(upload_root, f"{reference}.json")
    if not photo_path.is_file() or not metadata_path.is_file():
        raise LemioPhotoError("Uploaded photo is missing; check input/lemio_uploads retention")
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        source = SourcePhoto(**data)
    except (OSError, ValueError, TypeError) as exc:
        raise LemioPhotoError("Uploaded photo metadata is invalid") from exc
    if source.path != reference or photo_path.stat().st_size != source.size:
        raise LemioPhotoError("Uploaded photo metadata does not match the stored file")
    if sha256_file(photo_path) != source.sha256:
        raise LemioPhotoError("Uploaded photo checksum changed")
    return source
