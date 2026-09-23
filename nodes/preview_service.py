from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from PIL import Image

from .photo_types import LemioPhotoError, WorkingPhoto, safe_child, sha256_file


def create_preview(photo: WorkingPhoto, working_root: Path, max_width: int, max_height: int):
    if not 64 <= max_width <= 4096 or not 64 <= max_height <= 4096:
        raise LemioPhotoError("Preview bounds must be between 64 and 4096 pixels")
    path = safe_child(working_root, photo.path)
    if not path.is_file() or path.stat().st_size != photo.size or sha256_file(path) != photo.sha256:
        raise LemioPhotoError("Lemio · Create Preview: working JPEG is missing or changed")
    with Image.open(path) as source:
        source.load()
        image = source.convert("RGB")
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        array = np.asarray(image, dtype=np.float32) / np.float32(255.0)
    tensor = torch.from_numpy(np.ascontiguousarray(array)).unsqueeze(0)
    return tensor, int(array.shape[1]), int(array.shape[0])
