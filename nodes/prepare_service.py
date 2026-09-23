from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

from .photo_types import (
    JPEG_MAGIC,
    LemioPhotoError,
    SourcePhoto,
    WorkingPhoto,
    max_response_bytes,
    safe_child,
    save_metadata,
    sha256_file,
)


def processor_url() -> str:
    value = os.getenv("PHOTO_PROCESSOR_URL", "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise LemioPhotoError(
            "Lemio · Prepare Photo: PHOTO_PROCESSOR_URL is missing or invalid; "
            "configure an http(s) service URL"
        )
    return value


def _timeout() -> httpx.Timeout:
    try:
        connect = float(os.getenv("PHOTO_PIPELINE_CONNECT_TIMEOUT_SECONDS", "10"))
        read = float(os.getenv("PHOTO_PIPELINE_READ_TIMEOUT_SECONDS", "300"))
    except ValueError as exc:
        raise LemioPhotoError("Photo processor timeout settings must be numbers") from exc
    if connect <= 0 or read <= 0:
        raise LemioPhotoError("Photo processor timeout settings must be positive")
    return httpx.Timeout(connect=connect, read=read, write=read, pool=connect)


def _safe_error(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "unknown").split(";", 1)[0]
    return f"HTTP {response.status_code} ({content_type})"


def _validate_jpeg(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        if not handle.read(3).startswith(JPEG_MAGIC):
            raise LemioPhotoError("photo-processor returned non-JPEG content")
    try:
        with Image.open(path) as image:
            if image.format != "JPEG":
                raise LemioPhotoError("photo-processor response is not a JPEG")
            image.verify()
        with Image.open(path) as image:
            return image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise LemioPhotoError("photo-processor returned a damaged JPEG") from exc


def prepare_photo(
    source: SourcePhoto,
    upload_root: Path,
    working_root: Path,
    *,
    client: httpx.Client | None = None,
) -> WorkingPhoto:
    base_url = processor_url()
    source_path = safe_child(upload_root, source.path)
    if not source_path.is_file() or sha256_file(source_path) != source.sha256:
        raise LemioPhotoError("Lemio · Prepare Photo: source file is missing or changed")
    url_id = hashlib.sha256(base_url.encode()).hexdigest()[:16]
    cache_key = hashlib.sha256(f"{source.sha256}:{url_id}:prepare-v1".encode()).hexdigest()
    filename = f"{cache_key}.jpg"
    working_root.mkdir(parents=True, exist_ok=True)
    destination = safe_child(working_root, filename)
    metadata_path = safe_child(working_root, f"{filename}.json")
    if destination.is_file() and metadata_path.is_file():
        try:
            cached = WorkingPhoto(**json.loads(metadata_path.read_text(encoding="utf-8")))
            valid_cache = (
                cached.path == filename
                and cached.size == destination.stat().st_size
                and cached.sha256 == sha256_file(destination)
            )
            if valid_cache:
                _validate_jpeg(destination)
                return cached
        except (OSError, ValueError, TypeError, LemioPhotoError):
            pass

    temporary = working_root / f".{filename}.{uuid.uuid4().hex}.part"
    own_client = client is None
    http = client or httpx.Client(timeout=_timeout(), follow_redirects=False)
    try:
        try:
            with source_path.open("rb") as source_file:
                files = {"photo": (source.original_filename, source_file, source.mime_type)}
                with http.stream("POST", f"{base_url}/prepare", files=files) as response:
                    if not 200 <= response.status_code < 300:
                        raise LemioPhotoError(
                            f"Lemio · Prepare Photo: {_safe_error(response)} from photo-processor"
                        )
                    total = 0
                    with temporary.open("xb") as output:
                        for chunk in response.iter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > max_response_bytes():
                                raise LemioPhotoError(
                                    "Lemio · Prepare Photo: response exceeds configured size limit"
                                )
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
        except httpx.ConnectError as exc:
            raise LemioPhotoError(
                "Lemio · Prepare Photo: cannot connect to photo-processor at the configured URL. "
                "Check PHOTO_PROCESSOR_URL and Docker network app-network."
            ) from exc
        except httpx.TimeoutException as exc:
            raise LemioPhotoError(
                "Lemio · Prepare Photo: photo-processor request timed out; "
                "check service health and timeout settings"
            ) from exc
        width, height = _validate_jpeg(temporary)
        digest = sha256_file(temporary)
        size = temporary.stat().st_size
        os.replace(temporary, destination)
        result = WorkingPhoto(filename, filename, "image/jpeg", size, width, height, digest)
        try:
            save_metadata(metadata_path, result)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return result
    finally:
        temporary.unlink(missing_ok=True)
        if own_client:
            http.close()
