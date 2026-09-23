from __future__ import annotations

from pathlib import Path

import folder_paths
from aiohttp import web
from server import PromptServer

from .nodes.photo_types import LemioPhotoError, max_upload_bytes
from .nodes.upload_service import store_upload


@PromptServer.instance.routes.post("/lemio/photo-pipeline/upload")
async def upload_photo(request: web.Request):
    try:
        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "photo" or not field.filename:
            raise LemioPhotoError("multipart field 'photo' is required")
        # SpooledTemporaryFile keeps small files in memory and rolls larger files to disk.
        import tempfile

        with tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024) as spool:
            total = 0
            while chunk := await field.read_chunk(1024 * 1024):
                total += len(chunk)
                if total > max_upload_bytes():
                    raise LemioPhotoError("Upload exceeds PHOTO_PIPELINE_MAX_UPLOAD_MB")
                spool.write(chunk)
            spool.seek(0)
            result = store_upload(
                spool,
                field.filename,
                field.headers.get("Content-Type", "application/octet-stream"),
                Path(folder_paths.get_input_directory()) / "lemio_uploads",
            )
        return web.json_response(
            {
                "reference": result.path,
                "filename": result.original_filename,
                "size": result.size,
            }
        )
    except LemioPhotoError as exc:
        return web.json_response({"error": str(exc)}, status=400)
