from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import numpy as np
from PIL import Image, UnidentifiedImageError

from .photo_types import (
    DevelopParameters,
    FinalPhoto,
    LemioPhotoError,
    ProcessedPhoto,
    WorkingPhoto,
    safe_child,
    sha256_file,
)

SPECS = {
    "schema_version": ("integer", 1, 1),
    "exposure_ev": ("number", -2, 2),
    "temperature_shift": ("integer", -20, 20),
    "tint_shift": ("integer", -20, 20),
    "highlights": ("integer", -100, 100),
    "shadows": ("integer", -100, 100),
    "contrast": ("integer", -50, 50),
    "saturation": ("integer", -30, 30),
    "vibrance": ("integer", -50, 50),
    "tone_curve": ("enum", ["neutral", "low_contrast", "soft_contrast", "strong_contrast"]),
    "skin_tone": ("enum", ["keep", "reduce_redness", "slightly_warmer"]),
    "denoise": ("integer", 0, 100),
    "sharpen": ("integer", 0, 100),
}


def _service_url(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default or "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise LemioPhotoError(f"{name} is missing or invalid")
    return value


def _timeout(read_default: float = 300) -> httpx.Timeout:
    return httpx.Timeout(
        connect=float(os.getenv("PHOTO_PIPELINE_CONNECT_TIMEOUT_SECONDS", "10")),
        read=float(os.getenv("PHOTO_PIPELINE_READ_TIMEOUT_SECONDS", str(read_default))),
        write=float(os.getenv("PHOTO_PIPELINE_READ_TIMEOUT_SECONDS", str(read_default))),
        pool=10,
    )


def validate_develop(values: dict) -> dict:
    if not isinstance(values, dict) or set(values) != set(SPECS):
        raise LemioPhotoError("Develop parameters have missing or extra fields")
    result = {}
    for field, spec in SPECS.items():
        value = values[field]
        kind = spec[0]
        if kind == "enum":
            if value not in spec[1]:
                raise LemioPhotoError(f"Invalid develop parameter: {field}")
        elif kind == "integer":
            if type(value) is not int or not spec[1] <= value <= spec[2]:
                raise LemioPhotoError(f"Invalid develop parameter: {field}")
        elif (
            type(value) not in {int, float}
            or isinstance(value, bool)
            or not spec[1] <= value <= spec[2]
        ):
            raise LemioPhotoError(f"Invalid develop parameter: {field}")
        result[field] = float(value) if field == "exposure_ev" else value
    return result


def _develop_schema() -> dict:
    properties = {}
    for field, spec in SPECS.items():
        if spec[0] == "enum":
            properties[field] = {"type": "string", "enum": spec[1]}
        else:
            properties[field] = {"type": spec[0], "minimum": spec[1], "maximum": spec[2]}
    return {
        "type": "object",
        "properties": {
            "develop": {
                "type": "object",
                "properties": properties,
                "required": list(SPECS),
                "additionalProperties": False,
            },
            "analysis": {"type": "string"},
            "retouch_prompt": {"type": "string"},
        },
        "required": ["develop", "analysis", "retouch_prompt"],
        "additionalProperties": False,
    }


def _provider() -> str:
    provider = os.getenv("PHOTO_AI_PROVIDER", "openai").strip().lower()
    if provider not in {"openai", "bedrock"}:
        raise LemioPhotoError("PHOTO_AI_PROVIDER must be 'openai' or 'bedrock'")
    return provider


def _bedrock_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise LemioPhotoError("Amazon Bedrock requires the boto3 dependency") from exc
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
        config=Config(connect_timeout=10, read_timeout=600, retries={"max_attempts": 2}),
    )


def analyze_preview(tensor, client: httpx.Client | None = None) -> tuple[DevelopParameters, str]:
    array = tensor[0].detach().cpu().numpy() if hasattr(tensor, "detach") else np.asarray(tensor)[0]
    image = Image.fromarray(np.clip(array * 255, 0, 255).astype(np.uint8), "RGB")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    if _provider() == "bedrock":
        try:
            response = _bedrock_client().converse(
                modelId=os.getenv("BEDROCK_ANALYSIS_MODEL", "us.amazon.nova-lite-v1:0"),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "Analyze this photograph conservatively for "
                                    "professional development. Preserve identity, geometry, "
                                    "pose, clothing, background and composition. "
                                    "Call the supplied tool with the development plan."
                                )
                            },
                            {"image": {"format": "jpeg", "source": {"bytes": buffer.getvalue()}}},
                        ],
                    }
                ],
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": "lemio_photo_plan",
                                "description": (
                                    "Return the validated photo development and retouch plan"
                                ),
                                "inputSchema": {"json": _develop_schema()},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": "lemio_photo_plan"}},
                },
            )
            blocks = response["output"]["message"]["content"]
            parsed = next(block["toolUse"]["input"] for block in blocks if "toolUse" in block)
            params = DevelopParameters(validate_develop(parsed["develop"]), parsed["analysis"])
            return params, str(parsed["retouch_prompt"])
        except Exception as exc:
            raise LemioPhotoError("Lemio · Analyze Photo: Amazon Bedrock request failed") from exc

    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise LemioPhotoError("Lemio · Analyze Photo: OPENAI_API_KEY is not configured")
    data_url = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    body = {
        "model": os.getenv("PHOTO_ANALYSIS_MODEL", "gpt-6-luna"),
        "store": False,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Act as a conservative professional photo developer. "
                            "Analyze exposure, white balance, dynamic range, noise, "
                            "sharpness and portrait needs. Return relative adjustments "
                            "only. Do not change identity, geometry, pose, clothing, "
                            "background or composition."
                        ),
                    },
                    {"type": "input_image", "image_url": data_url, "detail": "high"},
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "lemio_photo_plan",
                "strict": True,
                "schema": _develop_schema(),
            }
        },
    }
    own = client is None
    http = client or httpx.Client(timeout=_timeout())
    try:
        response = http.post(
            _service_url("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/responses",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
        )
        if not response.is_success:
            raise LemioPhotoError(
                f"Lemio · Analyze Photo: OpenAI returned HTTP {response.status_code}"
            )
        payload = response.json()
        text = payload.get("output_text")
        if not text:
            for item in payload.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text = content.get("text")
                        break
        if not text:
            raise LemioPhotoError("Lemio · Analyze Photo: response contained no structured output")
        parsed = json.loads(text)
        params = DevelopParameters(validate_develop(parsed["develop"]), parsed["analysis"])
        return params, str(parsed["retouch_prompt"])
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        if isinstance(exc, LemioPhotoError):
            raise
        raise LemioPhotoError(
            "Lemio · Analyze Photo: request or response validation failed"
        ) from exc
    finally:
        if own:
            http.close()


def _artifact(path: Path, cls, filename: str):
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            mime = Image.MIME.get(image.format, "application/octet-stream")
    except (OSError, UnidentifiedImageError) as exc:
        raise LemioPhotoError("Image service returned a damaged image") from exc
    return cls(filename, filename, mime, path.stat().st_size, width, height, sha256_file(path))


def process_photo(
    working: WorkingPhoto,
    params: DevelopParameters,
    working_root: Path,
    output_root: Path,
    client=None,
):
    values = validate_develop(params.values)
    source = safe_child(working_root, working.path)
    key = hashlib.sha256((working.sha256 + json.dumps(values, sort_keys=True)).encode()).hexdigest()
    filename = f"{key}.jpg"
    destination = safe_child(output_root, filename)
    output_root.mkdir(parents=True, exist_ok=True)
    own = client is None
    http = client or httpx.Client(timeout=_timeout())
    temporary = output_root / f".{filename}.{uuid.uuid4().hex}.part"
    try:
        with source.open("rb") as handle:
            response = http.post(
                _service_url("PHOTO_PROCESSOR_URL") + "/process",
                files={"photo": (working.filename, handle, "image/jpeg")},
                data={"params": json.dumps(values, separators=(",", ":"))},
            )
        if not response.is_success:
            raise LemioPhotoError(
                f"Lemio · Process Photo: photo-processor returned HTTP {response.status_code}"
            )
        temporary.write_bytes(response.content)
        result = _artifact(temporary, ProcessedPhoto, filename)
        os.replace(temporary, destination)
        return result
    finally:
        temporary.unlink(missing_ok=True)
        if own:
            http.close()


def natural_retouch(
    processed: ProcessedPhoto, prompt: str, processed_root: Path, final_root: Path, client=None
):
    source = safe_child(processed_root, processed.path)
    source_bytes = source.read_bytes()
    instruction = (
        "Edit this photograph naturally and conservatively. Preserve identity, facial "
        "geometry, age, body shape, pose, hair, clothing, background, framing and "
        "composition. Preserve realistic skin texture; only reduce temporary blemishes "
        "and dark circles subtly, with slight eye/teeth cleanup "
        f"when appropriate. Additional analysis: {prompt[:4000]}"
    )
    if _provider() == "bedrock":
        try:
            with Image.open(io.BytesIO(source_bytes)) as original:
                width, height = original.size
                scale = min(1.0, (4190000 / (width * height)) ** 0.5, 4096 / max(width, height))
                width = max(320, int(width * scale) // 16 * 16)
                height = max(320, int(height * scale) // 16 * 16)
                prepared = original.convert("RGB")
                prepared.thumbnail((width, height), Image.Resampling.LANCZOS)
                canvas_input = io.BytesIO()
                prepared.save(canvas_input, "JPEG", quality=95)
            request = {
                "taskType": "IMAGE_VARIATION",
                "imageVariationParams": {
                    "images": [base64.b64encode(canvas_input.getvalue()).decode()],
                    "text": instruction,
                    "similarityStrength": 0.9,
                },
                "imageGenerationConfig": {
                    "numberOfImages": 1,
                    "quality": "premium",
                    "width": width,
                    "height": height,
                },
            }
            response = _bedrock_client().invoke_model(
                modelId=os.getenv("BEDROCK_RETOUCH_MODEL", "amazon.nova-canvas-v1:0"),
                body=json.dumps(request),
                accept="application/json",
                contentType="application/json",
            )
            payload = json.loads(response["body"].read())
            content = base64.b64decode(payload["images"][0], validate=True)
            return _save_final(content, final_root)
        except Exception as exc:
            raise LemioPhotoError("Lemio · Natural Retouch: Amazon Bedrock request failed") from exc

    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise LemioPhotoError("Lemio · Natural Retouch: OPENAI_API_KEY is not configured")
    # Image-edit providers generate at bounded resolutions.  Downscaling the request
    # avoids very slow relay uploads while preserving the untouched processed master.
    with Image.open(io.BytesIO(source_bytes)) as original:
        edit_input = original.convert("RGB")
        edit_input.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
        edit_buffer = io.BytesIO()
        edit_input.save(edit_buffer, "JPEG", quality=95)
        edit_bytes = edit_buffer.getvalue()
    form = {
        "model": os.getenv("PHOTO_RETOUCH_MODEL", "gpt-image-1.5"),
        "prompt": instruction,
        "input_fidelity": "high",
        "output_format": "jpeg",
        "output_compression": "95",
        "size": "auto",
        "n": "1",
    }
    own = client is None
    http = client or httpx.Client(timeout=_timeout(600))
    try:
        response = http.post(
            _service_url("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/images/edits",
            headers={"Authorization": f"Bearer {key}"},
            data=form,
            files={"image": (processed.filename, edit_bytes, "image/jpeg")},
        )
        if not response.is_success:
            raise LemioPhotoError(
                f"Lemio · Natural Retouch: OpenAI returned HTTP {response.status_code}"
            )
        payload = response.json()
        encoded = payload.get("b64_json")
        if not encoded and payload.get("data"):
            encoded = payload["data"][0].get("b64_json")
        if not encoded:
            raise LemioPhotoError("Lemio · Natural Retouch: response contained no image")
        content = base64.b64decode(encoded, validate=True)
        return _save_final(content, final_root)
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, LemioPhotoError):
            raise
        raise LemioPhotoError("Lemio · Natural Retouch: request or image decoding failed") from exc
    finally:
        if own:
            http.close()


def _save_final(content: bytes, final_root: Path) -> FinalPhoto:
    final_root.mkdir(parents=True, exist_ok=True)
    name = (
        f"lemio-{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
        f"{hashlib.sha256(content).hexdigest()[:8]}.jpg"
    )
    destination = safe_child(final_root, name)
    temporary = final_root / f".{name}.{uuid.uuid4().hex}.part"
    try:
        temporary.write_bytes(content)
        result = _artifact(temporary, FinalPhoto, name)
        os.replace(temporary, destination)
        return result
    finally:
        temporary.unlink(missing_ok=True)


def archive_photo(working, final, params, working_root, final_root, execution_id, client=None):
    working_path = safe_child(working_root, working.path)
    final_path = safe_child(final_root, final.path)
    own = client is None
    http = client or httpx.Client(timeout=_timeout())
    headers = {}
    token = os.getenv("PHOTO_ARCHIVE_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with working_path.open("rb") as w, final_path.open("rb") as f:
            response = http.post(
                _service_url("PHOTO_ARCHIVE_URL", "http://photo-archive:8000") + "/archive",
                headers=headers,
                files={
                    "working": ("working.jpg", w, "image/jpeg"),
                    "final": (final.filename, f, final.mime_type),
                },
                data={
                    "parameters": json.dumps(
                        validate_develop(params.values), separators=(",", ":")
                    ),
                    "execution_id": re.sub(r"[^A-Za-z0-9_-]", "-", str(execution_id))[:128]
                    or uuid.uuid4().hex,
                    "processed_at": datetime.now().astimezone().isoformat(),
                    "workflow_id": "comfyui-photo-pipeline",
                },
            )
        if response.status_code != 201:
            raise LemioPhotoError(
                f"Lemio · Archive Photo: archive service returned HTTP {response.status_code}"
            )
        payload = response.json()
        return payload.get("relative_directory", "archived")
    finally:
        if own:
            http.close()
