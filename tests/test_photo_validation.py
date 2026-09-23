from __future__ import annotations

import io

import pytest

from nodes.photo_types import LemioPhotoError, extension_for, safe_child, sha256_file
from nodes.upload_service import store_upload


@pytest.mark.parametrize("name", ["a.jpg", "A.JPEG", "x.png", "camera.nef", "camera.CR3", "x.arw"])
def test_allowed_extensions(name):
    assert extension_for(name).startswith(".")


@pytest.mark.parametrize("name", ["x", "x.gif", "x.exe", "bad\x00.jpg"])
def test_rejected_extensions(name):
    with pytest.raises(LemioPhotoError):
        extension_for(name)


@pytest.mark.parametrize("reference", ["../x.jpg", "/tmp/x.jpg", "a/../../x.jpg"])
def test_path_traversal_rejected(tmp_path, reference):
    with pytest.raises(LemioPhotoError):
        safe_child(tmp_path, reference)


def test_upload_uses_safe_name_and_sha(tmp_path, jpeg_bytes):
    content = jpeg_bytes()
    result = store_upload(io.BytesIO(content), "../../My Holiday.JPG", "text/plain", tmp_path)
    assert result.path != "My Holiday.JPG"
    assert result.path.endswith(".jpg")
    assert result.original_filename == "My Holiday.JPG"
    assert result.sha256 == sha256_file(tmp_path / result.path)
    assert (tmp_path / f"{result.path}.json").is_file()


def test_windows_path_is_removed_from_display_name(tmp_path, jpeg_bytes):
    result = store_upload(
        io.BytesIO(jpeg_bytes()),
        r"C:\Users\person\photo.jpg",
        "image/jpeg",
        tmp_path,
    )
    assert result.original_filename == "photo.jpg"


def test_bad_regular_image_signature_rejected(tmp_path):
    with pytest.raises(LemioPhotoError, match="not a JPEG"):
        store_upload(io.BytesIO(b"not jpeg"), "x.jpg", "image/jpeg", tmp_path)


def test_size_limit(monkeypatch, tmp_path, jpeg_bytes):
    monkeypatch.setenv("PHOTO_PIPELINE_MAX_UPLOAD_MB", "1")
    with pytest.raises(LemioPhotoError, match="exceeds"):
        store_upload(
            io.BytesIO(jpeg_bytes() + b"x" * (1024 * 1024)),
            "x.jpg",
            "image/jpeg",
            tmp_path,
        )
    assert not list(tmp_path.glob("*.part"))
