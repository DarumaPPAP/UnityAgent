---
name: unity-agent-full-e2e
description: Use when Codex must create a fixed UnityAgent E2E probe Scene, GameObject, Material and Script in a Unity project, then verify Compile, Editor PlayMode and Evidence with explicit approvals.
---

# UnityAgent Full E2E

Use the UnityAgent host CLI as the Codex Entry. Require the Unity Project path, the matching host and Unity Package revision, and an open Editor. Follow [the E2E capability guide](../../../../../docs/architecture/full-e2e-capability.md) for setup and result locations.

1. Run `unity-agent e2e plan --project-path <project>`; present `exact_diff`, `scene_object_diff` and `script_preview` to the user. This only saves the Plan outside the Project.
2. Obtain explicit approval for the reviewed Plan and separate permission for Scene save. Run `unity-agent e2e approve --project-path <project> --plan-id <id>` and `unity-agent e2e approve-save --project-path <project> --plan-id <id>` only when each permission is in scope.
3. Run `unity-agent e2e apply --project-path <project> --plan-id <id> --approval-ref <ref> --save-approval-ref <save-ref>`. Preserve the resulting `artifact_path`, `editor_result_artifact_path` when present, and `evidence_refs`.
4. Report Scene, Script, Material, Compile and PlayMode statuses separately. If the Editor is unavailable or a gate fails, report `blocked` and the remaining validation. Editor PlayMode does not establish Player or target device behavior.

Use the fixed workflow only. Never edit Scene YAML or the Asset Database outside the Editor APIs, invoke the Editor bridge or Provider directly, accept a freeform approval reference, or bypass the Control Plane and Tool Broker.

## Output Contract

Report Project path, Plan ID, approved asset and Scene object diff, each observed verification status, Evidence references and result artifact path. Distinguish unavailable and failed observations.

## Checklist

- [ ] Review the exact Plan before issuing either approval.
- [ ] Bind both approvals and Apply to the same Project and Plan.
- [ ] Check the saved Result Artifact and Evidence references.

## Common Mistakes

- Treating a fixture or a static test as a live Editor PlayMode result.
- Sending a generic `scene.mutate` request or calling the Editor bridge directly.
