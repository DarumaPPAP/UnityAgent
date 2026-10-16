# Private Production CI — Approval / durable State / Stage Resume

Status: **Host contract + private workflow template. NOT deployed to a Private repository; licensed Unity G1 remains BLOCKED_NOT_RUN.** This document does not establish Production E2E success.

## Boundary and ownership

- Public UnityAgent: reviewed source/Control Plane/Persistence, tests, and the **non-executable** workflow template at `ci/private/production-e2e.yml`.
- Private execution repository: protected workflow, private approval PRs and reviewer policy, its own Windows self-hosted runner. Never run the licensed runner from a public pull request. The public `.github/workflows/production-e2e.yml` now runs **Host contracts only**.
- Durable authority: `UNITYAGENT_STATE_ROOT` on an access-restricted, persistent Windows volume **outside** the Unity Project. It includes the canonical rock-import Plan, Blender Job/FBX, approvals, runs, snapshots, and Checkpoints. GitHub/Actions Artifact is **audit/backup only**, not authoritative State. Do not upload project assets, license files or tokens.
- Runner source: exactly one reviewed `main` commit SHA (`UNITYAGENT_APPROVED_SHA`), checked out to an isolated workspace. It is compared against the immutable Run registration. This is Development revision pinning, **not** Release.
- Control Plane remains the authority; Private Workflow cannot approve/dispatch mutations merely by accepting `workflow_dispatch` strings. Stage driver must invoke the existing Broker/Provider guarded operation. Local `rock-import approve` commands are **not** substitutes for Private approvals (`UNITYAGENT_REQUIRE_PRIVATE_APPROVAL=1`).

## Setup (operator-controlled; not workflow_dispatch)

1. Create a **private** execution repository and attach only isolated, graphics-capable, licensed Windows runners with labels `self-hosted, Windows, unity-6000.3.12f1, private-only`. Restrict the runner group to this repository. Protect its default branch, approval directory and production Environment. Do not share the runner with Public PR jobs.
2. Copy `ci/private/production-e2e.yml` to the Private repo's `.github/workflows/production-e2e.yml`. Configure protected vars `UNITYAGENT_STATE_ROOT`, `UNITYAGENT_APPROVED_SHA`, `UNITYAGENT_PRIVATE_APPROVERS` (explicit GitHub usernames), and `UNITYAGENT_PRIVATE_STAGE_DRIVER` (operator-installed, reviewed private script absolute path). `GITHUB_TOKEN` needs read access to private PR reviews, contents and collaborator metadata; unavailable/403 APIs deny approval. Token is never persisted or logged. For write-free access, no `contents:write` permission is required.
3. On the trusted host, create the Blender Job and `rock-import plan` with the existing Control Plane. Before dispatch, register once from the reviewed checkout:

   ```powershell
   $env:PYTHONPATH = "C:\reviewed\UnityAgent\src"
   python -m unityagent.control_plane.private_production_ci register `
       --state-root "D:\UnityAgentState" --run-id "rock-rock-g1" `
       --plan-id "<plan_id_from_rock_import_plan>" `
       --source-revision "<reviewed_40_character_main_SHA>"
   ```

   The Run ID is fixed as `rock-` + the Blender `job_id`; registration refuses mismatching FBX hash, Plan/Project Revision or pre-existing Run. Store registration/protected files under the runner account's restrictive ACL. State creation must not be callable by arbitrary dispatch inputs.

4. Submit a new approval PR **in the Private repository itself**, including `approvals/<run_id>/<stage>/<kind>.json`. Kinds: `artifact:stage`, `editor:mutation` **and separate** `editor:save`, `visual:stage`, `rollback:rollback`. The JSON contains exactly:

   ```json
   {
     "schema_version": "1.0",
     "run_id": "rock-rock-g1",
     "requested_stage": "editor",
     "kind": "mutation",
     "plan_id": "<exact_persisted_plan_id>",
     "plan_digest": "sha256:<exact_persisted_plan_hash>",
     "source_revision": "<reviewed_public_main_SHA>",
     "artifact_sha256": "<exact_staged_FBX_SHA256>",
     "project_revision": "sha256:<last_completed_stage_Project_hash>",
     "scope_paths": ["<exact_paths_from_immutable_Plan>"],
     "expires_at": "<RFC3339/ISO8601_UTC_expiry>"
   }
   ```

   These are **illustrative placeholders**, not production values. Take values from the immutable local Manifest/current Progress; do not type or infer paths or hashes. A reviewer on the configured allowlist with current write-level access must approve the **current PR head commit**. The PR author cannot self-approve. Changed head, dismissed review, changes requested, expired approval, mismatched Run/Plan/Scope, API failure and absent permission all block. Each operation requires its own PR number; local Decisions retain the GitHub attestation and are rechecked at Editor dispatch.

5. Trigger Private workflow with **existing** `run_id`, `stage` and `approval_pulls` JSON (e.g., `{"mutation":42,"save":43}`). Never provide local artifact paths, scripts, Provider IDs, arbitrary C# or Python via dispatch. The fixed stage order is:

   `artifact → editor → visual → rollback`.

   The operator-installed Stage driver is responsible for actual observed Gate JSON + hashed raw files in `<StateRoot>/evidence/<run_id>`. The bridge does **not** synthesize those observations. The private sample workflow refuses to run without this driver or Unity Editor.

## Stage transitions / Resume

| State | Condition | Result |
|---|---|---|
| `waiting` | Correct next Stage + new GitHub review + matching source/Plan/Project/Artifact + verified previous Checkpoints | `running`; durable unique Workflow Run ID and authenticated approval refs |
| `running` | Complete reports every Stage-required observed Gate with hashed raw evidence, and rechecks GitHub approval | Immutable receipt + canonical State snapshot/Checkpoint; next `waiting` or final `completed` |
| `running` interrupted, timed out or outcome unknown | No automatic redispatch. `RECONCILIATION_REQUIRED`; inspect Editor/Blender/Project side effects and evidence manually |
| Any State | Changed Project/Source/Plan, missing or tampered Checkpoint, stale review, expired/revoked scope, invalid evidence | Refuse; never silently rewrite State or approve |
| All four Stages | Nine G1 required Gates observed | `host_gate_contracts_complete=true`; `production_verified=false` until independent live Unity/Blender/human evidence audit |

The canonical `CheckpointStore` is State-only. Asset rollback is a separate, newly approved Editor operation with Receipt hash + GUID/ownership validation, not `CheckpointStore.restore`. Each new Stage has its own GitHub Workflow Run ID, while retaining the single logical `run_id`. Evidence files are hashed, but their raw filesystem provenance still needs a trusted operator-owned producer.

G1 required Gates: `production_runtime`, `blender_mcp`, `artifact_integrity`, `unity_compile`, `import_prefab_scene_guid`, `render_capture`, `visual_acceptance`, `rollback`, `lease_conflict`. `video_decode`, `hot_reload_comparison`, `g2`, and `g3` remain separately reported and do **not** block G1 by definition.

## Tests and current limitations

```sh
PYTHONPATH=src python -m unittest tests.runtime.test_private_production_ci tests.runtime.test_production_e2e_evidence -v
```

This is Host contract coverage (review/expiry/revocation/Run/Scope/Resume/Evidence and G1 aggregation), not a real Private GitHub approval, Unity Editor execution, visual human acceptance or operational failover test. Actual Private repo provisioning, Runner ACL verification, driver provisioning and live G1 evidence are **BLOCKED_NOT_RUN** until the Private deployment environment is available. The sample workflow alone must not be considered Production ready. Missing real Unity/Blender observations remain BLOCKED_NOT_RUN; never mark a fixture as Production success.
