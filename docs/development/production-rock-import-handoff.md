# UnityAgent Production Rock Handoff (Draft PR #199)

## Scope

The Blender MCP tool output is a **Staging artifact**, not the Unity E2E verdict. Only UnityAgent Control Plane can select and dispatch `scene.mutate` through `native_rock_import`.

Dependency chain: #195 → #196 → #197 → #198 → #199. No merge, release, remote dependency install, or Production Unity E2E PASS is implied.

### Blender MCP upstream compatibility

- Official `get_scene_info` returns formatted text; it does not expose `structuredContent.blender_session_identity`.
- An approved *fixed* Session probe obtains Addon/Protocol status and establishes a cooperative nonce on the live Blender WindowManager ID. It is rechecked while holding the Host session lock. A nonce is **not** authenticated process attestation or OS isolation, and third-party Blender Socket clients can bypass UnityAgent locks. Use a dedicated, isolated Blender instance.
- The launched MCP server receives `BLENDER_MCP_SAFE_MODE=1`. The fixed reviewed rock Template uses only Blender APIs, `math`, `json`, and allowed `mathutils`. It exports FBX; the host computes SHA-256 and writes `artifact.json`. Safe Mode is an AST filter, not a filesystem/socket sandbox.
- Unknown Addon status, changed Session, invalid Template output, untrusted Job, or ambiguous timeout **stops without resubmission**.

### Explicit Import operations

First obtain the completed `rock apply` Job and its Staging FBX.

```sh
unity-agent rock-import plan --project-path PROJECT --state-root OUTSIDE_PROJECT --job-id rock-g1
unity-agent rock-import approve --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --kind mutation
unity-agent rock-import approve --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --kind save
unity-agent rock-import apply --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --approval-ref MUTATION_REF --save-approval-ref SAVE_REF
```

The `plan` requires a matching completed Job and Artifact SHA-256, an empty exact `Assets/UnityAgentRockG1` target, a bound Project revision and fixed Definition. All Import/Save actions require distinct unexpired approvals.

The existing ToolBroker selects `native_rock_import` for `scene.mutate` qualified as `workflow=blender_rock_import`. Runtime acquires the project Editor lease. The bounded Provider stages only Rock.fbx and its current `.meta` preimage and invokes the **two allowlisted** fixed Unity Editor methods. There is no general-purpose `executeMethod` channel. The Editor process verifies its own approvals and writes a file-level Receipt for the importer, material, prefab and scene outputs.

Visual review, target Player, G2 and G3 remain separate required gates. `production_import=completed` is not `verified=true`.

### Separately approved rollback

```sh
unity-agent rock-import approve --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --kind rollback
unity-agent rock-import rollback --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --rollback-approval-ref ROLLBACK_REF
```

The Unity Editor revalidates the immutable Receipt hash, every owned file hash/GUID, and absence of unowned files before `AssetDatabase.DeleteAsset` on the fixed directory. Any conflicts or Editor failure stop and require reconciliation; no `git reset --hard` or raw Scene/Prefab/Material YAML edit is used.

## Required live validation

The following are **BLOCKED_NOT_RUN** until a licensed Unity 6000.3.12f1 Editor, URP and a supported graphics-capable Windows runner are connected:

- Real MCP Server + Addon version handshake + Session nonce through Safe Mode.
- Real Editor assembly Compile of `RockImportBridge.cs`.
- One Production Invoke of Blender → FBX → Broker → Editor → Material/Prefab/Scene → Receipt.
- QA evidence, scene visual acceptance, failed import recovery, controlled rollback and concurrent manual edit conflict.

Host tests and CI prove only Contracts, finite request/approval control, staging/receipt rejection and source/package integrity. They cannot replace live G1 evidence.

### Remaining caution

The Blender addon socket can be reached by non-cooperating local processes; the Session nonce and Lock cannot protect against them. The fixed Script is a bounded reviewed operation, but the MCP Server/Addon still require proper OS-level workspace/process isolation before untrusted production workloads. The C# bridge uses a fixed fixture-only target. General target paths and QA reasoning orchestration are future work, not implied by this PR.
