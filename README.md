# ComfyUI Photo Pipeline

ComfyUI Photo Pipeline adds a memory-conscious, end-to-end photo workflow to the ComfyUI canvas. It uploads and prepares a photo, asks a vision model for schema-constrained development parameters, calls RawTherapee through `photo-processor`, performs conservative natural AI retouching, generates a safe final filename, previews the result, and archives the working JPEG, parameters, and final image.

## Workflow

```mermaid
flowchart LR
  A[Lemio · Upload Photo] -->|LEMIO_SOURCE_PHOTO| B[Lemio · Prepare Photo]
  B -->|LEMIO_WORKING_PHOTO| C[Lemio · Create Preview]
  C -->|IMAGE| D[Lemio · Analyze Photo]
  D --> E[Lemio · Validate Develop Parameters]
  E --> F[Lemio · Process Photo]
  F --> G[Lemio · Natural Retouch]
  G --> H[Lemio · Create Final Preview]
  H --> I[Preview Image]
  B --> J[Lemio · Archive Photo]
  E --> J
  G --> J
```

The full-size source and working JPEG travel as immutable metadata objects containing controlled file references, sizes, hashes, and format metadata. They are never placed in workflow JSON and are never converted to tensors. Only the resized preview becomes a ComfyUI `IMAGE` tensor (BHWC float32, 0–1), keeping CPU memory use predictable.

## Supported uploads

- Standard images: `.jpg`, `.jpeg`, `.png`
- Camera RAW: `.dng`, `.nef`, `.cr2`, `.cr3`, `.arw`, `.orf`, `.rw2`, `.raf`, `.pef`, `.srw`

RAW decoding remains entirely the responsibility of `photo-processor`. RAW MIME types are not trusted or required. JPG and PNG uploads receive signature checks before storage.

## Nodes

### Lemio · Upload Photo

Choose or drag a local photo. The browser sends it to an authenticated ComfyUI-relative route; the server stores it under `input/lemio_uploads/` using a UUID filename. The serialized workflow contains only that controlled reference. Output: `LEMIO_SOURCE_PHOTO`.

### Lemio · Prepare Photo

Accepts `LEMIO_SOURCE_PHOTO`, streams multipart field `photo` to `${PHOTO_PROCESSOR_URL}/prepare`, validates the response as a readable JPEG, and atomically preserves the exact response bytes under `output/lemio_working/`. Outputs `LEMIO_WORKING_PHOTO` and a short status string.

The cache identity includes source SHA-256, a non-secret hash of the processor URL, and the preparation-contract version. Repeated identical work can reuse a checksum-verified result.

### Lemio · Create Preview

Accepts `LEMIO_WORKING_PHOTO`; `max_width` defaults to 1600 and `max_height` to 1200 (both 64–4096). It uses Lanczos resizing, preserves aspect ratio, and never enlarges a smaller photo. Outputs `IMAGE`, width, and height. Connect `IMAGE` to ComfyUI's built-in **Preview Image** node.

### Analysis, development, retouch, and archive

- **Lemio · Analyze Photo** sends only the bounded preview to either an OpenAI-compatible Responses API or Amazon Bedrock Converse and returns strict schema-v1 parameters plus a retouch prompt.
- **Lemio · Validate Develop Parameters** independently rejects missing, extra, mistyped, non-enum, or out-of-range fields.
- **Lemio · Process Photo** posts the unchanged working JPEG and validated JSON to `${PHOTO_PROCESSOR_URL}/process` and preserves the returned JPEG bytes.
- **Lemio · Natural Retouch** uses an OpenAI-compatible Images Edit endpoint or an image-editing model through Amazon Bedrock. Its fixed prompt preserves identity, geometry, age, pose, clothing, background, framing, and realistic skin texture.
- **Lemio · Create Final Preview** converts only a bounded final preview to a tensor.
- **Lemio · Archive Photo** sends working image, final image, canonical parameters, execution ID, and timestamp to `${PHOTO_ARCHIVE_URL}/archive`. It is an output node and intentionally creates a new append-only archive per execution.

## Installation

From the ComfyUI custom-node directory:

```bash
cd /data/comfyui/custom_nodes
git clone <YOUR_GIT_URL>/ComfyUI-Photo-Pipeline.git
cd ComfyUI-Photo-Pipeline
python -m pip install -r requirements.txt
```

Alternatively, use **ComfyUI Manager → Install via Git URL**, paste this repository's Git URL, and install. Restart ComfyUI after installation. The implementation uses the current ComfyUI V3 API (`comfy_api.latest`, `ComfyExtension`, and `comfy_entrypoint`) and the official frontend `app.registerExtension` mechanism; it requires a ComfyUI build that provides that API.

No local model, GPU package, database, worker, or additional listening service is installed. Torch, Pillow, and NumPy are supplied by ComfyUI; runtime HTTP/AWS dependencies are `httpx` and `boto3`.

## Portainer / Docker configuration

Attach both ComfyUI and `photo-processor` to the pre-existing external network and set the processor URL on the ComfyUI container:

```yaml
services:
  comfyui:
    environment:
      PHOTO_PROCESSOR_URL: http://photo-processor:8000
      PHOTO_ARCHIVE_URL: http://photo-archive:8000
      PHOTO_AI_PROVIDER: openai
      OPENAI_BASE_URL: https://your-compatible-gateway.example/v1
      OPENAI_API_KEY: supplied-by-secret-management
      PHOTO_ANALYSIS_MODEL: gpt-6-luna
      PHOTO_RETOUCH_MODEL: gpt-image-2.5-sunburst
      PHOTO_PIPELINE_MAX_UPLOAD_MB: "100"
      PHOTO_PIPELINE_MAX_RESPONSE_MB: "100"
      PHOTO_PIPELINE_CONNECT_TIMEOUT_SECONDS: "10"
      PHOTO_PIPELINE_READ_TIMEOUT_SECONDS: "300"
      PHOTO_RETOUCH_READ_TIMEOUT_SECONDS: "1200"
    networks:
      - app-network

networks:
  app-network:
    external: true
```

Do not publish a new port for this extension. Its upload route is registered on the existing ComfyUI server and called through `api.fetchApi`, so the existing loopback binding, tunnel, session, and authentication gateway remain in the request path. `PHOTO_PROCESSOR_URL` is read only on the server and is not stored in workflow JSON.

For Amazon Bedrock, set `PHOTO_AI_PROVIDER=bedrock`, `AWS_REGION`, `BEDROCK_ANALYSIS_MODEL` (default `us.openai.gpt-6.1-sol`) and `BEDROCK_RETOUCH_MODEL` (default `us.stability.stable-style-transfer-v1:0`). Use the normal AWS SDK credential chain, an attached workload role, or `AWS_BEARER_TOKEN_BEDROCK`; never put AWS credentials in a workflow. OpenAI-compatible and Bedrock configuration is selected exclusively server-side.

## Shortest usage path

1. Restart the ComfyUI container after installation and environment changes.
2. Load `examples/Lemio Full Photo Pipeline.json`, or add the nodes shown in the workflow diagram.
3. Choose or drop a photo, then queue the prompt from **Lemio · Archive Photo** or **Preview Image**.
4. For the defaults, confirm the displayed preview is no larger than 1600 × 1200.

## Storage and cleanup

Uploads are intentionally retained in `input/lemio_uploads/`, and prepared JPEGs in `output/lemio_working/`, so cached runs and reopened workflows remain valid. Successful full-pipeline runs send an append-only copy to `photo-archive`; the plugin never writes directly to the archive host path. Administrators must define retention and backup policies for uploads, working files, generated finals, and archive storage. Deleting referenced input or working files will make old workflows require another upload or prepare run.

The plugin rejects absolute paths, traversal, symlink escape, unsupported extensions, oversized uploads/responses, invalid ordinary-image signatures, and changed checksums. Temporary files are removed after failures, and final working files appear only after an atomic rename.

## Troubleshooting

- **Nodes do not appear:** inspect ComfyUI startup logs for import errors; update ComfyUI to a version with the V3 API; install `requirements.txt`; restart the container.
- **Cannot connect to photo-processor:** verify `PHOTO_PROCESSOR_URL`, that both containers joined `app-network`, and that the service name resolves inside the ComfyUI container.
- **Upload rejected before 100 MB:** ComfyUI's own server/proxy body-size setting may be lower. Raise it consistently at the trusted gateway and ComfyUI layer, while retaining an intentional limit.
- **Workflow opens but an upload is missing:** restore the referenced file and `.json` sidecar in `input/lemio_uploads/`, or upload the source again.
- **Invalid JPEG response:** check `/prepare` directly. HTML/JSON error pages and corrupt/truncated JPEGs are rejected and never promoted to working files.

## Testing

```bash
python -m pip install -e '.[test]'
# Only outside ComfyUI, install a CPU-only Torch build from the official index:
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
ruff check .
python -m compileall -q .
pytest -q
```

Tests mock HTTP and do not require a live processor, model, GPU, or running ComfyUI. CI runs lint, syntax compilation, and pytest on Python 3.13.

## Manual integration acceptance

On the target Portainer host, additionally verify a JPG, PNG, and at least one real camera RAW end to end. Confirm orientation visually, preview bounds, persistence across a container restart/workflow reopen, and byte identity by comparing the `/prepare` response SHA-256 with the corresponding file in `output/lemio_working/`. These hardware/container checks cannot be established by unit tests alone.
