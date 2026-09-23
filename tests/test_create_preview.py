from __future__ import annotations

import hashlib

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="ComfyUI supplies torch at runtime")

from nodes.photo_types import WorkingPhoto  # noqa: E402
from nodes.preview_service import create_preview  # noqa: E402


def working_photo(root, data, width, height):
    path = root / "work.jpg"
    path.write_bytes(data)
    return WorkingPhoto(
        path="work.jpg",
        filename="work.jpg",
        mime_type="image/jpeg",
        size=len(data),
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
    )


@pytest.mark.parametrize(
    ("source_size", "bounds", "expected"),
    [
        ((2000, 1000), (800, 800), (800, 400)),
        ((1000, 2000), (800, 800), (400, 800)),
        ((100, 50), (800, 800), (100, 50)),
        ((1600, 1200), (1000, 400), (533, 400)),
    ],
)
def test_preview_geometry(tmp_path, jpeg_bytes, source_size, bounds, expected):
    photo = working_photo(tmp_path, jpeg_bytes(source_size), *source_size)
    tensor, width, height = create_preview(photo, tmp_path, *bounds)
    assert (width, height) == expected
    assert tuple(tensor.shape) == (1, expected[1], expected[0], 3)
    assert tensor.dtype == torch.float32
    assert np.isfinite(tensor.numpy()).all()
    assert 0.0 <= tensor.min().item() <= tensor.max().item() <= 1.0


def test_bounds_validation(tmp_path, jpeg_bytes):
    photo = working_photo(tmp_path, jpeg_bytes(), 80, 40)
    with pytest.raises(Exception, match="between 64 and 4096"):
        create_preview(photo, tmp_path, 63, 1200)
