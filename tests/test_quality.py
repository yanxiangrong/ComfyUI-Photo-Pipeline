import json
from dataclasses import replace

import httpx
import numpy as np
import pytest
from PIL import Image

from nodes.photo_types import FinalPhoto, LemioPhotoError, sha256_file
from nodes.quality_service import validate_retouch_result
from nodes.semantic_quality import semantic_quality


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


def test_semantic_quality_blocks_added_person(monkeypatch, tmp_path):
    monkeypatch.setenv("PHOTO_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    original = artifact(tmp_path, "original.jpg", np.full((128, 128, 3), 128, dtype=np.uint8))

    def handler(request):
        body = json.loads(request.content)
        assert len(body["input"][0]["content"]) == 3
        return httpx.Response(
            200,
            json={
                "output_text": json.dumps(
                    {
                        "people_added_or_removed": True,
                        "main_scene_replaced": False,
                        "severe_anatomy_defect": False,
                        "review": "Added a person to an empty landscape",
                    }
                )
            },
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(LemioPhotoError, match="content fidelity failed"),
    ):
        semantic_quality(original, original, tmp_path, tmp_path, client=client)
