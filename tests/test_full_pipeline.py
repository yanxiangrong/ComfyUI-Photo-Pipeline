from __future__ import annotations

import base64
import hashlib
import io
import json

import httpx
import numpy as np
import pytest

from nodes.full_pipeline_service import (
    SPECS,
    analyze_preview,
    archive_photo,
    natural_retouch,
    process_photo,
    validate_develop,
)
from nodes.photo_types import DevelopParameters, LemioPhotoError, WorkingPhoto


def neutral():
    return {
        "schema_version": 1,
        "exposure_ev": 0,
        "temperature_shift": 0,
        "tint_shift": 0,
        "highlights": 0,
        "shadows": 0,
        "contrast": 0,
        "saturation": 0,
        "vibrance": 0,
        "tone_curve": "neutral",
        "skin_tone": "keep",
        "denoise": 0,
        "sharpen": 0,
    }


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def working(root, content, size=(80, 40)):
    root.mkdir()
    (root / "working.jpg").write_bytes(content)
    return WorkingPhoto(
        "working.jpg",
        "working.jpg",
        "image/jpeg",
        len(content),
        *size,
        hashlib.sha256(content).hexdigest(),
    )


def test_validate_develop_strict():
    assert set(validate_develop(neutral())) == set(SPECS)
    invalid = neutral()
    invalid["contrast"] = 51
    with pytest.raises(LemioPhotoError, match="contrast"):
        validate_develop(invalid)
    invalid = neutral() | {"extra": 1}
    with pytest.raises(LemioPhotoError, match="missing or extra"):
        validate_develop(invalid)


def test_openai_analysis_structured_output(monkeypatch):
    monkeypatch.setenv("PHOTO_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    planned = {"develop": neutral(), "analysis": "balanced", "retouch_prompt": "subtle"}

    def handler(request):
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        assert body["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,")
        return httpx.Response(200, json={"output_text": json.dumps(planned)})

    params, prompt = analyze_preview(
        np.zeros((1, 32, 64, 3), dtype=np.float32), client=mock_client(handler)
    )
    assert params.values == neutral()
    assert params.analysis == "balanced"
    assert prompt == "subtle"


def test_process_preserves_service_bytes(monkeypatch, tmp_path, jpeg_bytes):
    monkeypatch.setenv("PHOTO_PROCESSOR_URL", "http://photo-processor:8000")
    source_bytes = jpeg_bytes((80, 40))
    result_bytes = jpeg_bytes((80, 40), (10, 20, 30))
    source_root = tmp_path / "working"
    item = working(source_root, source_bytes)

    def handler(request):
        assert request.url.path == "/process"
        body = request.read()
        assert b'name="photo"' in body and b'name="params"' in body
        return httpx.Response(200, content=result_bytes)

    result = process_photo(
        item,
        DevelopParameters(neutral()),
        source_root,
        tmp_path / "processed",
        mock_client(handler),
    )
    assert (tmp_path / "processed" / result.path).read_bytes() == result_bytes


def test_openai_retouch_and_archive(monkeypatch, tmp_path, jpeg_bytes):
    monkeypatch.setenv("PHOTO_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("PHOTO_ARCHIVE_URL", "http://photo-archive:8000")
    image = jpeg_bytes((64, 32))
    processed_root = tmp_path / "processed"
    processed = working(processed_root, image, (64, 32))

    def edit_handler(request):
        body = request.read()
        assert b'name="image"' in body
        assert b'name="input_fidelity"' in body
        assert b"high" in body
        assert b"\xff\xd8\xff" in body
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(image).decode()}]})

    final = natural_retouch(
        processed,
        "subtle",
        processed_root,
        tmp_path / "final",
        mock_client(edit_handler),
    )

    working_root = tmp_path / "working"
    original = working(working_root, image, (64, 32))

    def archive_handler(request):
        assert request.url.path == "/archive"
        assert b'name="working"' in request.read()
        return httpx.Response(201, json={"relative_directory": "2026-01-01-000000-test"})

    relative = archive_photo(
        original,
        final,
        DevelopParameters(neutral()),
        working_root,
        tmp_path / "final",
        "node-7",
        mock_client(archive_handler),
    )
    assert relative == "2026-01-01-000000-test"


def test_bedrock_style_transfer_retouch(monkeypatch, tmp_path, jpeg_bytes):
    monkeypatch.setenv("PHOTO_AI_PROVIDER", "bedrock")
    monkeypatch.setenv(
        "BEDROCK_RETOUCH_MODEL", "us.stability.stable-style-transfer-v1:0"
    )
    image = jpeg_bytes((64, 32))
    processed_root = tmp_path / "processed"
    processed = working(processed_root, image, (64, 32))

    class Bedrock:
        def invoke_model(self, **kwargs):
            assert kwargs["modelId"] == "us.stability.stable-style-transfer-v1:0"
            request = json.loads(kwargs["body"])
            assert request["init_image"] == request["style_image"]
            assert request["change_strength"] == 0.1
            payload = {"images": [base64.b64encode(image).decode()]}
            return {"body": io.BytesIO(json.dumps(payload).encode())}

    final = natural_retouch(
        processed,
        "subtle",
        processed_root,
        tmp_path / "final",
        Bedrock(),
    )
    assert (tmp_path / "final" / final.path).read_bytes() == image
