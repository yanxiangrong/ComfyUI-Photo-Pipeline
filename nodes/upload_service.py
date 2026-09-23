from __future__ import annotations

import os
import uuid
from pathlib import Path

from .photo_types import (
    LemioPhotoError,
    SourcePhoto,
    extension_for,
    max_upload_bytes,
    save_metadata,
    sha256_file,
    validate_signature,
)


def store_upload(stream, original_filename: str, mime_type: str, upload_root: Path) -> SourcePhoto:
    display_name = Path(original_filename.replace("\\", "/")).name
    extension = extension_for(display_name)
    upload_root.mkdir(parents=True, exist_ok=True)
    reference = f"{uuid.uuid4().hex}{extension}"
    destination = upload_root / reference
    temporary = upload_root / f".{reference}.part"
    total = 0
    try:
        with temporary.open("xb") as output:
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_upload_bytes():
                    raise LemioPhotoError("Upload exceeds PHOTO_PIPELINE_MAX_UPLOAD_MB")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if total == 0:
            raise LemioPhotoError("Uploaded file is empty")
        validate_signature(temporary, extension)
        digest = sha256_file(temporary)
        os.replace(temporary, destination)
        photo = SourcePhoto(
            path=reference,
            original_filename=display_name,
            mime_type=mime_type or "application/octet-stream",
            size=total,
            sha256=digest,
            extension=extension,
        )
        save_metadata(upload_root / f"{reference}.json", photo)
        return photo
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        (upload_root / f"{reference}.json").unlink(missing_ok=True)
        raise
