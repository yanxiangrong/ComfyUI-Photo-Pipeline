# Production acceptance — release 0.2.0

Local verification: ruff, compileall and pytest; 39 passed and one skipped (local Torch unavailable).
GitHub Actions additionally runs with CPU Torch on Python 3.13. No model download is required.

The production exercise uses existing uploaded JPG, a PNG converted losslessly from that image,
and a real Nikon D70s compressed NEF from the processor's documented public test source.
Each case executes prepare, initial AI analysis, one feedback review, deterministic processing,
one AI retouch, automatic quality validation and append-only archive.

Detailed results, initial/final parameters and source references are saved privately in ComfyUI
`output/lemio_acceptance/release-0.2.0.json`. Image files and personal prompts are not committed.

| Case | State | Archive |
| --- | --- | --- |
| JPG / natural beauty | Passed, 101.18 seconds | `20261020170757-7277` |
| PNG / high-end retouch | Transport passed; visual FAILED (added person to landscape) | `20261020171001-7401` |
| Real Nikon NEF / natural beauty | Transport passed, 79.87 seconds | `20261020171120-7480` |

For the JPG archive, the actual saved working/final bytes match the manifest SHA-256 values.
The manifest contains beauty direction and one development review. Quality warnings are preserved
for inspection; warnings do not certify visual identity or anatomy. A warning is not a failed decode.

The full workflow is saved under the ComfyUI user's workflows with a persistent source reference,
template and feedback mode. The previous saved workflow was backed up before replacement.

Pending acceptance is not counted as passed: visual comparison of face/body templates, multiple
people, the operator's own camera format, browser rendering and near-20-minute timeout behavior.
Template calibration remains a documentation-only plan as requested; this release is not a claim
that all six presets have been visually calibrated.

Visual inspection found a critical limitation: the high-end beauty prompt invented a person in a
harbor landscape. Pixel checks did not detect this semantic change. The prompt has been strengthened
to forbid adding people or objects and to restrict non-portrait inputs to tonal/color improvements.
This is a prompt mitigation, not a certified semantic guard. This historical test archive remains as
failure evidence and must not be presented as a validated beauty result.
