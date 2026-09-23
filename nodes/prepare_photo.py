from __future__ import annotations

import hashlib
from pathlib import Path

import folder_paths
from comfy_api.latest import io

from .photo_types import SourcePhoto
from .prepare_service import prepare_photo, processor_url

SOURCE = io.Custom("LEMIO_SOURCE_PHOTO")
WORKING = io.Custom("LEMIO_WORKING_PHOTO")


class LemioPreparePhoto(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioPreparePhoto",
            display_name="Lemio · Prepare Photo",
            category="Lemio/Photo Pipeline",
            inputs=[SOURCE.Input("source_photo")],
            outputs=[WORKING.Output("working_photo"), io.String.Output("status")],
        )

    @classmethod
    def fingerprint_inputs(cls, source_photo: SourcePhoto):
        url_id = hashlib.sha256(processor_url().encode()).hexdigest()[:16]
        return f"{source_photo.sha256}:{url_id}:prepare-v1"

    @classmethod
    def execute(cls, source_photo: SourcePhoto):
        result = prepare_photo(source_photo, _upload_root(), _working_root())
        status = f"{result.width}×{result.height}, {result.size / 1024 / 1024:.1f} MiB"
        return io.NodeOutput(result, status)


def _upload_root() -> Path:
    return Path(folder_paths.get_input_directory()) / "lemio_uploads"


def _working_root() -> Path:
    return Path(folder_paths.get_output_directory()) / "lemio_working"
