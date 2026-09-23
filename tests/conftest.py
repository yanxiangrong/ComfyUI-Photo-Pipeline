from __future__ import annotations

import io

import pytest
from PIL import Image


@pytest.fixture
def jpeg_bytes():
    def make(size=(80, 40), color=(20, 100, 200)):
        output = io.BytesIO()
        Image.new("RGB", size, color).save(output, format="JPEG", quality=95)
        return output.getvalue()

    return make
