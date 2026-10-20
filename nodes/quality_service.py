"""Bounded CPU checks; no identity or aesthetic claims."""

from __future__ import annotations

import numpy as np
from PIL import Image, UnidentifiedImageError

from .photo_types import LemioPhotoError, safe_child, sha256_file


def validate_retouch_result(final, reference, final_root, reference_root):
    path = safe_child(final_root, final.path)
    if sha256_file(path) != final.sha256 or path.stat().st_size != final.size:
        raise LemioPhotoError("Lemio · Validate Retouch Result: final checksum mismatch")
    try:
        with Image.open(path) as probe:
            probe.verify()
        with Image.open(path) as source:
            width, height = source.size
            if width * height > 100_000_000 or min(width, height) < min(
                64, reference.width, reference.height
            ):
                raise LemioPhotoError("Lemio · Validate Retouch Result: invalid final dimensions")
            image = source.convert("RGB")
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        with Image.open(safe_child(reference_root, reference.path)) as source:
            original = source.convert("RGB").resize(image.size, Image.Resampling.LANCZOS)
    except (OSError, UnidentifiedImageError) as exc:
        raise LemioPhotoError("Lemio · Validate Retouch Result: unreadable image") from exc
    pixels = np.asarray(image, dtype=np.float32)
    baseline = np.asarray(original, dtype=np.float32)
    luminance = pixels @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    original_luma = baseline @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    if float(luminance.std()) < 0.5 and float(original_luma.std()) > 5:
        raise LemioPhotoError(
            "Lemio · Validate Retouch Result: final image collapsed to a flat image"
        )
    if float((luminance <= 2).mean()) > 0.99 and float((original_luma <= 2).mean()) < 0.95:
        raise LemioPhotoError("Lemio · Validate Retouch Result: final image is nearly black")
    if float((luminance >= 253).mean()) > 0.99 and float((original_luma >= 253).mean()) < 0.95:
        raise LemioPhotoError("Lemio · Validate Retouch Result: final image is nearly white")
    warnings = []
    aspect_change = abs((width / height) / (reference.width / reference.height) - 1)
    if aspect_change > 0.03:
        warnings.append("aspect ratio changed by more than 3%; inspect framing")
    difference = float(np.abs(pixels - baseline).mean() / 255)
    if difference > 0.30:
        warnings.append("large image difference; inspect identity and composition")
    if (width, height) != (reference.width, reference.height):
        warnings.append("output dimensions differ from input")
    return {
        "version": 1,
        "status": "warning" if warnings else "passed",
        "width": width,
        "height": height,
        "mean_luminance": round(float(luminance.mean()), 3),
        "normalized_pixel_difference": round(difference, 5),
        "warnings": warnings,
        "limitations": "No face recognition, identity, anatomy or aesthetic verification",
    }
