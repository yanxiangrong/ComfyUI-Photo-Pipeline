WEB_DIRECTORY = "./js"

try:
    from comfy_api.latest import ComfyExtension
except ModuleNotFoundError as exc:
    # The service-layer unit tests run outside a ComfyUI checkout. Do not hide
    # missing transitive imports when ComfyUI itself is actually available.
    if exc.name not in {"comfy_api", "comfy_api.latest"}:
        raise
else:
    from . import routes as _routes  # noqa: F401 - registers the ComfyUI route
    from .nodes.create_preview import LemioCreatePreview
    from .nodes.full_pipeline import (
        LemioAnalyzePhoto,
        LemioArchivePhoto,
        LemioCreateFinalPreview,
        LemioDevelopWithFeedback,
        LemioNaturalRetouch,
        LemioProcessPhoto,
        LemioRetouchDirection,
        LemioValidateDevelopParameters,
    )
    from .nodes.prepare_photo import LemioPreparePhoto
    from .nodes.upload_photo import LemioUploadPhoto

    class LemioPhotoPipelineExtension(ComfyExtension):
        async def get_node_list(self):
            return [
                LemioUploadPhoto,
                LemioPreparePhoto,
                LemioCreatePreview,
                LemioRetouchDirection,
                LemioAnalyzePhoto,
                LemioValidateDevelopParameters,
                LemioDevelopWithFeedback,
                LemioProcessPhoto,
                LemioNaturalRetouch,
                LemioCreateFinalPreview,
                LemioArchivePhoto,
            ]

    async def comfy_entrypoint():
        return LemioPhotoPipelineExtension()
