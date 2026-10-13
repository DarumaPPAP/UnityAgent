# UnityArtistCLI final acceptance audit

Date: 2026-09-11 (JST)
Audited revision: `11937ca` (`migration/unity-artist-cli-v2`)
Authority: `01_GOAL_AND_DEFINITION_OF_DONE.md`, `08_ACCEPTANCE_AND_TEST_PLAN.md`, `09_CODEX_MASTER_PROMPT.md`, `12_UNITY_VERSION_PIPELINE_SUPPORT.md`, and the repository contracts.

## Result

Overall state: **PARTIAL_VERIFIED**

Completion state: `partial_verified`

Production-ready: `false`

All four release-matrix rows now have direct fixture evidence on this host. The
Unity 2022.3 row is verified through the required Official Unity CLI/Pipeline
first-candidate gate followed by a fixed, bounded non-MCP batch fallback after
the concrete Unity 6-only Pipeline incompatibility was observed. The remaining
partial state is limited to an external Official Unity CLI global-help parser
limitation and an unobserved Marketplace UI import; neither is silently marked
as passed.

## Definition of Done audit

| Area | Status | Evidence / reason |
|---|---|---|
| A. CLI-first architecture and cutover | PASS | UnityAgent keeps the existing Capability → Provider Registry → Resolver → Dispatcher → Provider Adapter → Evidence chain; the production package has no MCP runtime dependency and legacy MyUnityMCP remains migration-only. |
| B. Artist capability boundary | PASS | UnityArtistCLI is limited to Artist inspection, LookDev, lighting, environment, camera, cinematic/Timeline, capture, evaluation, and refinement; generic CRUD and arbitrary C# execution are not exposed. |
| C. Safety and evidence lifecycle | PASS | JSON contracts, support preflight, expected-revision checks, opaque approval token, exact diffs, Undo registration, no implicit save, and separate save ownership are covered by CLI, Editor, fallback, and release validators. |
| D. Codex plugin / Marketplace contract | PASS | UnityAgent provider/routing/catalog entries, the skill-only `unity-artist` plugin manifests, marketplace contract, PR publication, and CI contract checks are present. Actual Marketplace UI import is not claimed as observed. |
| E. Unity 6 Built-in matrix row | PASS | Direct fixture and UnityAgent → UnityArtistCLI → Unity/Pipeline E2E evidence pass in `unity6-builtin-e2e-evidence.yaml`. |
| F. Unity 6 URP matrix row | PASS | Primary visual fixture, native URP `ColorAdjustments` Volume transaction, capture/evaluate/refine, and 3-shot Cinemachine Timeline evidence pass in `unity6-urp-primary-visual-evidence.yaml` and `unity6-urp-cinematic-evidence.yaml`. |
| G. Unity 2022.3 LTS + Built-in row | PASS | Official Pipeline was exhaustively probed first on Unity `2022.3.22f1` with CLI `1.0.0-beta.8`; every listed version returned the concrete Unity 6.0 requirement. The fixed `unity run` batch fallback then passed the complete Artist lifecycle and safety checks in `unity2022-3-builtin-bounded-fallback-evidence.yaml`. |
| H. Unity 6 HDRP matrix row | PASS | Full Official Pipeline-authored HDRP fixture, native `Fog` Volume transaction, capture/evaluate/refine loop, and 3-shot Cinemachine Timeline evidence pass in `unity6-hdrp-primary-visual-evidence.yaml` and `unity6-hdrp-cinematic-evidence.yaml`. |
| I. Tests, validation, documentation, and decision log | PASS | Host build/tests, static validators, UnityAgent canonical validation, live Unity recompile, all four matrix evidence verifiers, the bounded-fallback verifier, updated specs/catalogs/README, and the 2026-09-11 Decision Log are included. |

## Mandatory Unity 2022.3 scenario audit

Status: **PASS**

The official Unity CLI/Pipeline gate was tested before fallback selection. The
exhaustive evidence lists `0.6.0-exp.1`, `0.5.0-exp.1`, `0.4.0-exp.1`,
`0.3.1-exp.1`, `0.3.0-exp.1`, and `0.2.0-exp.2`; all failed with the concrete
message that the Pipeline package requires Unity 6.0 or later. The fallback is
restricted to Unity 2022.3 LTS + Built-in and the fixed
`UnityArtist.UnityArtistBatchCommands.Dispatch` method.

The disposable fixture passed compile-error inspection, inspect → plan →
preview, the no-token approval rejection, exact-diff apply with Undo and no
save, 1920×1080 capture, explicit human evaluation, linked refinement/apply,
and cross-process history. The fallback uses the shared `ArtistSession`; it
does not add a Player Framework, execute dynamic code, mutate raw Unity YAML,
use MCP, expose generic CRUD, or persist approval tokens.

## Mandatory URP scenario audit

Status: **PASS**

The official Unity CLI/Pipeline-authored URP fixture contains the required
subject and goal proxies, courtyard geometry, directional light, camera,
reflection probe, Volume/profile, materials, fog direction, and compressed
three-shot Timeline. The observed lifecycle includes inspect → capture → plan →
preview → approval guard → apply → save → evaluate/refine. The final capture
is 1920×1080 and the final human review decision is `accepted`.

The native URP Volume adapter verified and persisted a `ColorAdjustments`
component with `postExposure=-0.6` and `contrast=15`, with exact diff, Undo
registration, and no implicit save. The direct capture renderer did not
produce a distinct pixel hash for the post-processing camera toggle; therefore
the Volume claim is supported by native profile inspection and transaction
evidence, while visual review is attributed to the authored scene and camera
composition rather than an inferred pixel delta.

## Mandatory HDRP scenario audit

Status: **PASS**

The official Unity CLI/Pipeline-authored HDRP fixture contains the required
subject and goal proxies, courtyard geometry, directional light, camera,
reflection probe, native HDRP Volume/Fog profile, HDRP materials, and compressed
three-shot Timeline. The observed lifecycle includes inspect → capture → plan →
preview → approval guard → apply → save → evaluate/refine. The initial capture
was explicitly reviewed as `needs_refine`; the post-refinement 1920×1080
capture was explicitly accepted.

The native HDRP adapter verified and applied `HDRP.Fog.meanFreePath` from `400`
to `28.5714`, with exact diff, Undo registration, and no implicit save. The
separate cinematic evidence verifies all three Main Camera Brain bindings, all
three virtual-camera references, clip timing, and the marker track. Unity 6
HDRP's known package-resource warnings remain classified in the evidence and
did not prevent command execution or capture.

## Remaining partial items

1. The installed Official Unity CLI beta intercepts `unity artist --help` as a
   global help flag before plugin dispatch. `unity artist help` and standalone
   `unity-artist --help` pass; the intercepted form remains explicitly recorded
   as `blocked_by_official_cli_global_parser`.
2. A real Codex Marketplace UI import was not performed in this non-UI turn.
   The plugin manifests, marketplace entry, PR publication, and CI checks are
   validated; no Marketplace UI result is represented as a false PASS.

Merging is intentionally not performed without an explicit merge request.
