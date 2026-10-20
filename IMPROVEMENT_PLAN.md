# Improvement decisions — 2026-10-20

## Implemented in this release

`parameters.json` now contains manifest version 2: final develop parameters, initial parameters,
review rounds and proposals, review count, template and override levels, provider/model identifiers,
development/retouch durations, artifact hashes/dimensions and the final quality report. No credentials,
service URLs, host paths, or source image bytes are included. Existing archives remain unchanged.
Consumers of the old flat JSON must read `develop` in v2. The archive API and three-file layout remain
compatible. Free-text user instructions and review summaries may contain personal information;
administrators must protect archive access and backups accordingly.

Final images automatically undergo checksum, decode, dimension, blank/black/white collapse checks.
Aspect changes and large pixel differences generate warnings in the manifest, not aesthetic claims.
This does not detect identity drift, bad hands, distorted clothing or anatomical errors.

## Beauty template calibration — documentation only

Scope clarification: this product processes portraits. Do not expand non-portrait routing or landscape
handling. Format/RAW fixtures without people verify transport only; they do not qualify as beauty or
body-shaping acceptance. Prioritize consenting portrait fixtures and real half/full-body evaluation.

Build a consented evaluation set covering close-up, half-body, full-body, multiple people, different
skin tones, lighting, ages and clothing. Render each of the six templates against the same source,
then compare face/body low, medium and high independently. Record model, prompt version, settings,
identity fidelity, skin texture, garment/background distortion, preference and latency. Keep template
names provisional until visual evaluation; prompt presets are authored, not empirically calibrated.

## Regional control — documentation only

Current editing uses full-image prompts. Plan optional subject selection, separate face/body enable
switches and masks. Preserve jewelry, hands, clothing edges and background lines. Test multiple-person
targeting before enabling it. A prompt cannot guarantee pixel-faithful identity or background.

## Deterministic development — documentation only

Current 8-bit JPEG workflow limits RAW latitude. Evaluate 16-bit intermediate storage, linear-light
operations, more native RawTherapee adjustments, face-aware skin correction and better denoising.
Use paired reference images, clipped-pixel statistics and visual tests before changing the contract.
Maintain schema versions and compare neutral renders to avoid hidden color shifts.

## Feedback reviewer independence — documentation only

The same model currently proposes and reviews parameters. Compare a separate reviewer model or
blind side-by-side evaluation against the current reviewer. Extend objective metrics to channel
clipping, skin exposure and sharpening halos. Metrics should inform decisions rather than enforce
one aesthetic. Keep the existing maximum of two reviews until improvements are demonstrated.

## Per-round parameter limits — documentation only

Specify bounded revisions (candidate exposure delta 0.5 EV, other deltas calibrated per control).
Reject excessive changes explicitly rather than silently clamp. Test oscillation, accepting unchanged
parameters, review-cap exhaustion and reverting to a demonstrably better prior candidate. Record
proposals and decisions in the manifest. No new delta limit is enabled in this release.

## Long image requests — research, no provider migration enabled

Official sources checked on 2026-10-20:

- [Image editing API](https://developers.openai.com/api/reference/resources/images/methods/edit)
- [Background Responses](https://developers.openai.com/api/docs/guides/background)
- [Image generation](https://developers.openai.com/api/docs/guides/image-generation)

Images editing supports streaming events; streaming is still a live connection and is not a durable
job ID. Responses background mode offers polling, but this does not establish that the current relay
supports background image editing or preserves the same image model/options. Its compatibility must
be tested separately. A model-list response or OPTIONS route alone is not proof of task support.

Recommended capability experiment: explicitly submit one small image using the selected model and
streaming; record event types and completion without logging image payloads. Separately submit a
background Responses image edit, persist the returned ID, poll status and verify output/model parity.
Only enable a transport when the relay documents and passes that contract. Require a total monotonic
deadline, bounded response bytes, restart recovery, cancellation semantics and duplicate billing tests.
Never retry an ambiguous timed-out edit automatically, switch models, or reuse AI output as a cache.

Current production retains the explicit synchronous Images Edit transport and 1200-second read timeout.
An authenticated, non-generating OPTIONS probe of the relay returned HTTP 404 for both
`/images/edits` and `/responses` on 2026-10-20. Since normal POST requests to these routes work,
the OPTIONS results establish only that capability discovery is unavailable, not lack of async support.
An HTTP read timeout measures idle reads, not a strict total wall-clock deadline. A future transport
must add a total deadline as well. Streaming may improve progress visibility but cannot guarantee
survival across gateway disconnects. Durable asynchronous support remains unverified for this relay.
