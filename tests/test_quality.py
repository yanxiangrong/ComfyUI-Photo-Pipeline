from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from nodes.photo_types import FinalPhoto, LemioPhotoError, sha256_file
from nodes.quality_service import validate_retouch_result


def artifact(root, name, pixels):
    path = root / name
    Image.fromarray(pixels).save(path, "JPEG", quality=95)
    height, width = pixels.shape[:2]
    return FinalPhoto(
        name, name, "image/jpeg", path.stat().st_size, width, height, sha256_file(path)
    )


def test_quality_passes_realistic_detail_and_detects_collapse(tmp_path):
    rng = np.random.default_rng(12)
    original = artifact(
        tmp_path, "original.jpg", rng.integers(40, 220, (128, 128, 3), dtype=np.uint8)
    )
    report = validate_retouch_result(original, original, tmp_path, tmp_path)
    assert report["status"] == "passed"
    flat = artifact(tmp_path, "flat.jpg", np.full((128, 128, 3), 128, dtype=np.uint8))
    with pytest.raises(LemioPhotoError, match="flat image"):
        validate_retouch_result(flat, original, tmp_path, tmp_path)
    with pytest.raises(LemioPhotoError, match="checksum"):
        validate_retouch_result(replace(original, sha256="wrong"), original, tmp_path, tmp_path)


def test_quality_warns_on_aspect_change(tmp_path):
    original = artifact(tmp_path, "original.jpg", np.full((128, 128, 3), 128, dtype=np.uint8))
    final = artifact(tmp_path, "final.jpg", np.full((128, 192, 3), 128, dtype=np.uint8))
    report = validate_retouch_result(final, original, tmp_path, tmp_path)
    assert report["status"] == "warning"
    assert any("aspect" in warning for warning in report["warnings"])
