from __future__ import annotations

import folder_paths
from comfy_api.latest import io

from .photo_types import load_source

SOURCE = io.Custom("LEMIO_SOURCE_PHOTO")


class LemioUploadPhoto(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioUploadPhoto",
            display_name="Lemio · Upload Photo",
            category="Lemio/Photo Pipeline",
            description=(
                "Upload a JPG, PNG, or supported camera RAW without decoding it into a tensor."
            ),
            inputs=[io.String.Input("source_ref", default="", socketless=True)],
            outputs=[SOURCE.Output("source_photo")],
        )

    @classmethod
    def fingerprint_inputs(cls, source_ref: str):
        source = load_source(_upload_root(), source_ref)
        return source.sha256

    @classmethod
    def execute(cls, source_ref: str):
        return io.NodeOutput(load_source(_upload_root(), source_ref))


def _upload_root():
    from pathlib import Path

    return Path(folder_paths.get_input_directory()) / "lemio_uploads"
