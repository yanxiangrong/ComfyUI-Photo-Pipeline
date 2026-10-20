from __future__ import annotations

import json
from pathlib import Path

import folder_paths
from comfy_api.latest import io

from .full_pipeline_service import (
    PRESETS,
    analyze_preview,
    archive_photo,
    develop_with_feedback,
    make_retouch_direction,
    natural_retouch,
    process_photo,
    validate_develop,
)
from .photo_types import (
    DevelopParameters,
    FinalPhoto,
    ProcessedPhoto,
    RetouchDirection,
    WorkingPhoto,
)
from .preview_service import create_preview

DEVELOP = io.Custom("LEMIO_DEVELOP_PARAMETERS")
WORKING = io.Custom("LEMIO_WORKING_PHOTO")
PROCESSED = io.Custom("LEMIO_PROCESSED_PHOTO")
FINAL = io.Custom("LEMIO_FINAL_PHOTO")
DIRECTION = io.Custom("LEMIO_RETOUCH_DIRECTION")


class LemioRetouchDirection(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioRetouchDirection",
            display_name="Lemio · Retouch Direction",
            category="Lemio/Photo Pipeline",
            inputs=[
                io.Combo.Input("preset", options=list(PRESETS), default="自然美颜"),
                io.Combo.Input("strength", options=["低", "中", "高"], default="中"),
                io.Combo.Input("skin", options=["跟随模板", "低", "中", "高"], default="跟随模板"),
                io.Combo.Input(
                    "face",
                    options=["跟随模板", "关闭", "低", "中", "高"],
                    default="跟随模板",
                ),
                io.Combo.Input(
                    "body",
                    options=["跟随模板", "关闭", "低", "中", "高"],
                    default="跟随模板",
                ),
                io.Combo.Input(
                    "lighting", options=["跟随模板", "低", "中", "高"], default="跟随模板"
                ),
                io.Combo.Input("background", options=["严格保持", "轻微整理"], default="严格保持"),
                io.String.Input(
                    "custom_instructions",
                    multiline=True,
                    default="",
                    placeholder="可选：例如保留雀斑、不要美白",
                ),
            ],
            outputs=[DIRECTION.Output("retouch_direction"), io.String.Output("summary")],
        )

    @classmethod
    def execute(cls, preset, strength, skin, face, body, lighting, background, custom_instructions):
        result = make_retouch_direction(
            preset, strength, skin, face, body, lighting, background, custom_instructions
        )
        summary = (
            f"{preset} · 整体{strength} · 肤质{skin} · 脸部{face} · "
            f"美体{body} · 光影{lighting} · 背景{background}"
        )
        return io.NodeOutput(result, summary)


class LemioAnalyzePhoto(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioAnalyzePhoto",
            display_name="Lemio · Analyze Photo",
            category="Lemio/Photo Pipeline",
            inputs=[
                io.Image.Input("preview"),
                DIRECTION.Input("retouch_direction", optional=True),
            ],
            outputs=[
                DEVELOP.Output("develop_parameters"),
                io.String.Output("retouch_prompt"),
                io.String.Output("analysis"),
            ],
        )

    @classmethod
    def execute(cls, preview, retouch_direction: RetouchDirection | None = None):
        params, prompt = analyze_preview(preview, direction=retouch_direction)
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
        result = DevelopParameters(
            values, develop_parameters.analysis, develop_parameters.provenance
        )
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
        if working_photo is None or develop_parameters is None:
            return float("nan")
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


class LemioDevelopWithFeedback(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioDevelopWithFeedback",
            display_name="Lemio · Develop With Feedback",
            category="Lemio/Photo Pipeline",
            inputs=[
                WORKING.Input("working_photo"),
                DEVELOP.Input("develop_parameters"),
                io.Combo.Input(
                    "review_mode",
                    options=["关闭", "一次", "最多两次"],
                    default="一次",
                ),
                DIRECTION.Input("retouch_direction", optional=True),
            ],
            outputs=[
                PROCESSED.Output("processed_photo"),
                DEVELOP.Output("final_parameters"),
                io.String.Output("review_status"),
            ],
            not_idempotent=True,
        )

    @classmethod
    def execute(
        cls,
        working_photo: WorkingPhoto,
        develop_parameters: DevelopParameters,
        review_mode: str,
        retouch_direction: RetouchDirection | None = None,
    ):
        processed, final_parameters, status = develop_with_feedback(
            working_photo,
            develop_parameters,
            review_mode,
            _working_root(),
            _processed_root(),
            retouch_direction,
        )
        return io.NodeOutput(processed, final_parameters, status)


class LemioCreateProcessedPreview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LemioCreateProcessedPreview",
            display_name="Lemio · Create Processed Preview",
            category="Lemio/Photo Pipeline",
            inputs=[
                PROCESSED.Input("processed_photo"),
                io.Int.Input("max_width", default=1600, min=64, max=4096),
                io.Int.Input("max_height", default=1200, min=64, max=4096),
            ],
            outputs=[
                io.Image.Output("preview"),
                io.Int.Output("width"),
                io.Int.Output("height"),
            ],
        )

    @classmethod
    def execute(cls, processed_photo: ProcessedPhoto, max_width: int, max_height: int):
        image, width, height = create_preview(
            processed_photo, _processed_root(), max_width, max_height
        )
        return io.NodeOutput(image, width, height)


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
                DIRECTION.Input("retouch_direction", optional=True),
            ],
            outputs=[FINAL.Output("final_photo"), io.String.Output("filename")],
            not_idempotent=True,
        )

    @classmethod
    def execute(
        cls,
        processed_photo: ProcessedPhoto,
        retouch_prompt: str,
        retouch_direction: RetouchDirection | None = None,
    ):
        result = natural_retouch(
            processed_photo,
            retouch_prompt,
            _processed_root(),
            _final_root(),
            direction=retouch_direction,
        )
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
