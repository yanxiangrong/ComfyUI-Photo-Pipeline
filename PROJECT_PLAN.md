# Project plan and status

This is the source-of-truth implementation status for the ComfyUI photo workflow. Update it with every material workflow change; README documents usage, while this file records scope and acceptance.

## Implemented

- Version-2 archive manifest with development review history, beauty settings, model identifiers,
  hashes, durations and automatic final-image quality report.
- Automatic final checksum/decode/dimension/collapse checks; aspect and large-difference warnings.
- A final vision comparison blocks obvious changes in people count, scene replacement and severe
  anatomical defects; this is an additional analysis call, not a biometric guarantee.
- Documentation-only enhancement designs and asynchronous transport research in IMPROVEMENT_PLAN.md.

- Persistent JPG, PNG, and camera RAW upload references.
- `/prepare` working JPEG with byte-preserving storage and bounded ComfyUI previews.
- Schema-constrained AI development analysis and independent parameter validation.
- Deterministic `/process` development using the complete schema-v1 parameter set.
- Bounded development feedback: disabled, one review by default, or at most two reviews. Each revision is reapplied to the original working JPEG and AI results are not cached.
- Beauty-direction presets for skin, face, body, lighting, and background handling.
- One final generative Natural Retouch after development feedback is complete.
- Final preview, safe filename, and append-only archive.
- OpenAI-compatible relay provider and retained Amazon Bedrock provider design.

## Acceptance evidence

- Unit tests cover upload safety, exact `/prepare` bytes, previews, strict parameters, development review, retouch, and archive requests.
- `photo-processor` container tests verify every schema-v1 control changes pixels, combined/ablated adjustments, JPEG/PNG, and a real Nikon NEF chain.
- Production `photo-processor` was probed independently for all 12 adjustment controls.
- Production ComfyUI registers the V3 Lemio nodes after restart.
- GitHub Actions runs on Python 3.13 for this repository.

## Remaining production checks

- Run and visually compare the same real portrait with `自然美颜`, `全身塑形`, and `高级精修`.
- Completed: production generated half-body portrait run with one development review, initial/final
  parameters, semantic quality and archive `20261020171756-7876` (see ACCEPTANCE.md).
- Completed: restart plus saved widget/source persistence checked through the ComfyUI queue. Browser
  interaction and the operator's own real portrait collection remain to be evaluated.
- Run the latest full workflow with a real PNG and the operator's current camera RAW format.
- Redeploy `photo-archive` from its published immutable image rather than relying on its earlier emergency hot patch.

## Deliberate limits

- Feedback reviews only deterministic tonal/color/detail development; face and body edits happen once in Natural Retouch.
- Review iterations are capped at two to prevent cost, latency, oscillation, and repeated subjective changes.
- The working JPEG is 8-bit sRGB, so later development cannot recover sensor data or already clipped highlights.
- Bedrock remains optional; the active production route uses the configured OpenAI-compatible relay until a suitable Bedrock image-edit model is available.
