"""Vision-model comparison for obvious content drift; not biometric verification."""

import base64
import io
import json
import os

import httpx
from PIL import Image

from .photo_types import LemioPhotoError, safe_child


def semantic_quality(final, reference, final_root, reference_root, client=None):
    images = []
    for root, item in [(reference_root, reference), (final_root, final)]:
        with Image.open(safe_child(root, item.path)) as source:
            image = source.convert("RGB")
            image.thumbnail((1600, 1200), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=90)
            images.append(buffer.getvalue())
    instruction = (
        "Compare image 1 (source) to image 2 (edited result). Check content fidelity, not beauty. "
        "Report added or removed people, replacement of the main scene, or obvious severe anatomy "
        "defects. Normal skin cleanup, moderate face/body refinement, exposure/color improvements "
        "and resolution changes are permitted. Only mark a failure when clearly visible. "
        "Return the supplied schema."
    )
    flags = ["people_added_or_removed", "main_scene_replaced", "severe_anatomy_defect"]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {**{key: {"type": "boolean"} for key in flags}, "review": {"type": "string"}},
        "required": [*flags, "review"],
    }
    provider = os.getenv("PHOTO_AI_PROVIDER", "openai")
    try:
        if provider == "bedrock":
            from .full_pipeline_service import _bedrock_client

            response = (client or _bedrock_client()).converse(
                modelId=os.getenv("BEDROCK_ANALYSIS_MODEL", "us.openai.gpt-6.1-sol"),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"text": instruction},
                            *[
                                {"image": {"format": "jpeg", "source": {"bytes": value}}}
                                for value in images
                            ],
                        ],
                    }
                ],
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": "lemio_quality",
                                "description": "Check edited image fidelity",
                                "inputSchema": {"json": schema},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": "lemio_quality"}},
                },
            )
            parsed = next(
                block["toolUse"]["input"]
                for block in response["output"]["message"]["content"]
                if "toolUse" in block
            )
        else:
            from .full_pipeline_service import _service_url, _timeout

            own = client is None
            http = client or httpx.Client(timeout=_timeout())
            try:
                response = http.post(
                    _service_url("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/responses",
                    headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                    json={
                        "model": os.getenv("PHOTO_ANALYSIS_MODEL", "gpt-6-luna"),
                        "store": False,
                        "input": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": instruction},
                                    *[
                                        {
                                            "type": "input_image",
                                            "detail": "high",
                                            "image_url": "data:image/jpeg;base64,"
                                            + base64.b64encode(value).decode(),
                                        }
                                        for value in images
                                    ],
                                ],
                            }
                        ],
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "strict": True,
                                "name": "lemio_quality",
                                "schema": schema,
                            }
                        },
                    },
                )
                response.raise_for_status()
                payload = response.json()
                text = payload.get("output_text") or next(
                    content["text"]
                    for item in payload.get("output", [])
                    for content in item.get("content", [])
                    if content.get("type") == "output_text"
                )
                parsed = json.loads(text)
            finally:
                if own:
                    http.close()
        if set(parsed) != {*flags, "review"} or any(type(parsed[key]) is not bool for key in flags):
            raise ValueError("invalid quality schema")
        report = {
            **{key: parsed[key] for key in flags},
            "review": str(parsed["review"])[:1500],
            "status": "failed" if any(parsed[key] for key in flags) else "passed",
        }
    except Exception as exc:
        raise LemioPhotoError(
            "Lemio · Validate Retouch Result: semantic quality request or validation failed"
        ) from exc
    if report["status"] == "failed":
        raise LemioPhotoError(
            "Lemio · Validate Retouch Result: content fidelity failed: " + report["review"]
        )
    return report
