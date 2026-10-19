from __future__ import annotations

import json
from pathlib import Path

import folder_paths
from comfy_api.latest import io

from .full_pipeline_service import (
    analyze_preview,
    archive_photo,
    natural_retouch,
    process_photo,
    validate_develop,
)
from .photo_types import DevelopParameters, FinalPhoto, ProcessedPhoto, WorkingPhoto
from .preview_service import create_preview

DEVELOP = io.Custom("LEMIO_DEVELOP_PARAMETERS")
WORKING = io.Custom("LEMIO_WORKING_PHOTO")
PROCESSED = io.Custom("LEMIO_PROCESSED_PHOTO")
FINAL = io.Custom("LEMIO_FINAL_PHOTO")


class LemioAnalyzePhoto(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioAnalyzePhoto",
            display_name="Lemio · Analyze Photo",
            category="Lemio/Photo Pipeline",
            inputs=[io.Image.Input("preview")],
            outputs=[
                DEVELOP.Output("develop_parameters"),
                io.String.Output("retouch_prompt"),
                io.String.Output("analysis"),
            ],
        )

    @classmethod
    def execute(cls, preview):
        params, prompt = analyze_preview(preview)
        return io.NodeOutput(params, prompt, params.analysis)


class LemioValidateDevelopParameters(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioValidateDevelopParameters",
            display_name="Lemio · Validate Develop Parameters",
            category="Lemio/Photo Pipeline",
            inputs=[DEVELOP.Input("develop_parameters")],
            outputs=[DEVELOP.Output("validated_parameters"), io.String.Output("parameters_json")],
        )

    @classmethod
    def execute(cls, develop_parameters: DevelopParameters):
        values = validate_develop(develop_parameters.values)
        result = DevelopParameters(values, develop_parameters.analysis)
        return io.NodeOutput(result, json.dumps(values, ensure_ascii=False, separators=(",", ":")))


class LemioProcessPhoto(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioProcessPhoto",
            display_name="Lemio · Process Photo",
            category="Lemio/Photo Pipeline",
            inputs=[WORKING.Input("working_photo"), DEVELOP.Input("develop_parameters")],
            outputs=[PROCESSED.Output("processed_photo"), io.String.Output("status")],
        )

    @classmethod
    def fingerprint_inputs(cls, working_photo: WorkingPhoto, develop_parameters: DevelopParameters):
        return f"{working_photo.sha256}:{json.dumps(develop_parameters.values, sort_keys=True)}"

    @classmethod
    def execute(cls, working_photo: WorkingPhoto, develop_parameters: DevelopParameters):
        result = process_photo(
            working_photo,
            develop_parameters,
            _working_root(),
            _processed_root(),
        )
        return io.NodeOutput(
            result, f"{result.width}×{result.height}, {result.size / 1048576:.1f} MiB"
        )


class LemioNaturalRetouch(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioNaturalRetouch",
            display_name="Lemio · Natural Retouch",
            category="Lemio/Photo Pipeline",
            inputs=[
                PROCESSED.Input("processed_photo"),
                io.String.Input("retouch_prompt", multiline=True),
            ],
            outputs=[FINAL.Output("final_photo"), io.String.Output("filename")],
        )

    @classmethod
    def execute(cls, processed_photo: ProcessedPhoto, retouch_prompt: str):
        result = natural_retouch(processed_photo, retouch_prompt, _processed_root(), _final_root())
        return io.NodeOutput(result, result.filename)


class LemioCreateFinalPreview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioCreateFinalPreview",
            display_name="Lemio · Create Final Preview",
            category="Lemio/Photo Pipeline",
            inputs=[
                FINAL.Input("final_photo"),
                io.Int.Input("max_width", default=1600, min=64, max=4096),
                io.Int.Input("max_height", default=1200, min=64, max=4096),
            ],
            outputs=[io.Image.Output("preview"), io.Int.Output("width"), io.Int.Output("height")],
        )

    @classmethod
    def execute(cls, final_photo: FinalPhoto, max_width: int, max_height: int):
        image, width, height = create_preview(final_photo, _final_root(), max_width, max_height)
        return io.NodeOutput(image, width, height)


class LemioArchivePhoto(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioArchivePhoto",
            display_name="Lemio · Archive Photo",
            category="Lemio/Photo Pipeline",
            inputs=[
                WORKING.Input("working_photo"),
                FINAL.Input("final_photo"),
                DEVELOP.Input("develop_parameters"),
            ],
            outputs=[io.String.Output("archive_directory")],
            hidden=[io.Hidden.unique_id],
            is_output_node=True,
            not_idempotent=True,
        )

    @classmethod
    def execute(
        cls,
        working_photo: WorkingPhoto,
        final_photo: FinalPhoto,
        develop_parameters: DevelopParameters,
    ):
        relative = archive_photo(
            working_photo,
            final_photo,
            develop_parameters,
            _working_root(),
            _final_root(),
            str(cls.hidden.unique_id),
        )
        return io.NodeOutput(relative)


def _working_root() -> Path:
    return Path(folder_paths.get_output_directory()) / "lemio_working"


def _processed_root() -> Path:
    return Path(folder_paths.get_output_directory()) / "lemio_processed"


def _final_root() -> Path:
    return Path(folder_paths.get_output_directory()) / "lemio_final"
