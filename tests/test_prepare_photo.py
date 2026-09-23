from __future__ import annotations

import io

import httpx
import pytest

from nodes.photo_types import LemioPhotoError
from nodes.prepare_service import prepare_photo
from nodes.upload_service import store_upload


def make_source(tmp_path, data):
    upload = tmp_path / "input"
    return store_upload(io.BytesIO(data), "source.jpg", "image/jpeg", upload), upload


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_prepare_preserves_response_bytes(monkeypatch, tmp_path, jpeg_bytes):
    monkeypatch.setenv("PHOTO_PROCESSOR_URL", "http://photo-processor:8000")
    source, upload = make_source(tmp_path, jpeg_bytes((20, 10)))
    expected = jpeg_bytes((101, 53))

    def handler(request):
        assert request.url.path == "/prepare"
        assert b'name="photo"' in request.read()
        return httpx.Response(200, content=expected, headers={"content-type": "image/jpeg"})

    result = prepare_photo(source, upload, tmp_path / "output", client=client_for(handler))
    assert (tmp_path / "output" / result.path).read_bytes() == expected
    assert (result.width, result.height) == (101, 53)


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_http_errors(monkeypatch, tmp_path, jpeg_bytes, status):
    monkeypatch.setenv("PHOTO_PROCESSOR_URL", "http://processor:8000")
    source, upload = make_source(tmp_path, jpeg_bytes())
    client = client_for(lambda request: httpx.Response(status, json={"private": "not leaked"}))
    with pytest.raises(LemioPhotoError, match=f"HTTP {status}"):
        prepare_photo(source, upload, tmp_path / "output", client=client)


@pytest.mark.parametrize(
    ("error", "message"),
    [(httpx.ConnectError("down"), "cannot connect"), (httpx.ReadTimeout("slow"), "timed out")],
)
def test_network_errors(monkeypatch, tmp_path, jpeg_bytes, error, message):
    monkeypatch.setenv("PHOTO_PROCESSOR_URL", "http://processor:8000")
    source, upload = make_source(tmp_path, jpeg_bytes())

    def handler(request):
        raise error

    with pytest.raises(LemioPhotoError, match=message):
        prepare_photo(source, upload, tmp_path / "output", client=client_for(handler))


@pytest.mark.parametrize("body", [b"<html>error</html>", b"\xff\xd8\xffbroken"])
def test_invalid_jpeg(monkeypatch, tmp_path, jpeg_bytes, body):
    monkeypatch.setenv("PHOTO_PROCESSOR_URL", "http://processor:8000")
    source, upload = make_source(tmp_path, jpeg_bytes())
    client = client_for(lambda request: httpx.Response(200, content=body))
    with pytest.raises(LemioPhotoError, match="JPEG"):
        prepare_photo(source, upload, tmp_path / "output", client=client)
    assert not list((tmp_path / "output").glob("*.part"))


def test_response_too_large(monkeypatch, tmp_path, jpeg_bytes):
    monkeypatch.setenv("PHOTO_PROCESSOR_URL", "http://processor:8000")
    monkeypatch.setenv("PHOTO_PIPELINE_MAX_RESPONSE_MB", "1")
    source, upload = make_source(tmp_path, jpeg_bytes())
    client = client_for(lambda request: httpx.Response(200, content=b"x" * (1024 * 1024 + 1)))
    with pytest.raises(LemioPhotoError, match="size limit"):
        prepare_photo(source, upload, tmp_path / "output", client=client)


def test_missing_url(tmp_path, jpeg_bytes, monkeypatch):
    monkeypatch.delenv("PHOTO_PROCESSOR_URL", raising=False)
    source, upload = make_source(tmp_path, jpeg_bytes())
    with pytest.raises(LemioPhotoError, match="missing or invalid"):
        prepare_photo(source, upload, tmp_path / "output")
