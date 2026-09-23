from __future__ import annotations

from pathlib import Path

import folder_paths
from comfy_api.latest import io

from .photo_types import WorkingPhoto
from .preview_service import create_preview

WORKING = io.Custom("LEMIO_WORKING_PHOTO")


class LemioCreatePreview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioCreatePreview",
            display_name="Lemio · Create Preview",
            category="Lemio/Photo Pipeline",
            inputs=[
                WORKING.Input("working_photo"),
                io.Int.Input("max_width", default=1600, min=64, max=4096, step=1),
                io.Int.Input("max_height", default=1200, min=64, max=4096, step=1),
            ],
            outputs=[io.Image.Output("preview"), io.Int.Output("width"), io.Int.Output("height")],
        )

    @classmethod
    def execute(cls, working_photo: WorkingPhoto, max_width: int, max_height: int):
        image, width, height = create_preview(working_photo, _working_root(), max_width, max_height)
        return io.NodeOutput(image, width, height)


def _working_root() -> Path:
    return Path(folder_paths.get_output_directory()) / "lemio_working"
