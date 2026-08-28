# Architecture v3.1 Migration Plan

Status: Phase 0 plan  
Branch: `refactor/architecture-v3-1-phase0`  
Final source of truth: `DarumaPPAP/UnityAgent`

## Goal

Reorganize UnityAgent into seven authoritative modules without weakening the existing user-specific Unity development policy, while eliminating the long-term two-repository execution split.

```text
UnityAgent/
├─ AGENTS.md
├─ Policy/
├─ Context/
├─ Orchestration/
├─ Runtime/
├─ Persistence/
├─ Operations/
├─ Eval/
├─ .agents/
├─ SkillReferences/
└─ docs/
```

No new top-level `Core/`, `Common/`, `Shared/`, `Tools/`, or `Schemas/` ownership bucket is introduced.

## Migration safety rules

- `main` is never edited directly.
- Existing user policy is migrated losslessly before any legacy source is removed.
- Golden/expected evaluation content never enters a production Runtime prompt.
- Canonical Runtime facts are transported structurally; they are not reconstructed from a lossy alternate representation.
- Runtime/Evaluator infrastructure defects are not counted as Agent behavior regression.
- Fake-runtime tests are supporting tests only; boundary changes require historical artifact replay and controlled Production Smoke.
- `.ai` deletion, compatibility deletion, Graph-repo archive/read-only transition, and `main` merge are Human Gates.
- Every phase updates this migration record and stops on unexplained regression.

## Phase 0 — Architecture Contract Freeze

### Changes allowed

- architecture contract documentation
- inventory and dependency mapping
- split/delete lists
- version/resume compatibility design
- Harness health contract
- migration validators that do not alter production behavior

### Changes forbidden

- bulk file movement
- deleting `.ai`
- moving production execution from Graph repo
- changing user policy semantics
- changing production prompt behavior
- changing mutation/approval boundaries

### Exit criteria

- each current high-risk file/module has one target authority or an explicit `SPLIT` plan
- no competing authoritative owner remains unresolved in the plan
- split seams are testable
- Human reviewer can see exact deletion/archive gates

## Phase 1 — Canonical Contracts

Create canonical contracts next to their owning modules before copying implementations.

Required contract families:

- `Runtime/Contracts/ExecutionResult`
- `Runtime/Contracts/ExecutionEvidence`
- `Runtime/Contracts/MutationEvidence`
- `Runtime/Contracts/RuntimeFailure`
- `Persistence/Contracts/EvidenceRecord`
- `Persistence/Contracts/ExecutionState`
- `Persistence/Contracts/WorkflowState`
- `Persistence/Contracts/LoopControlState`
- `Persistence/Contracts/RunCheckpoint`
- `Persistence/Contracts/SessionRecord`
- `Persistence/Contracts/MemoryRecord`
- `Operations/Observability/TraceRecord`
- `Eval/Attribution/EvalRecord`
- `Eval/GoldenContracts/GoldenContract`

### Core invariant

Runtime and Eval must not derive the same fact with incompatible parsers. In particular, `changed_paths`, gate outcomes, tool identity, timeout/protocol failure, evidence refs, and mutation scope must have one canonical structured representation.

### Exit

Historical production bundles can be normalized into the new contracts with no loss of canonical facts.

## Phase 2 — Policy + Context

### Policy

1. Copy `.ai/user-policy.yaml` losslessly to `Policy/User/user-policy.yaml`.
2. Move risk/security/approval/evidence rule definitions under Policy.
3. Split `.ai/harness/mcp-activation.yaml`: selection/permission requirements -> Policy; actual tool exposure -> Runtime.
4. Add Policy validators and policy revision/fingerprint.

### Context

1. Move Prompt to `Context/Prompt/` after no-Golden-leak review.
2. Move Context Packs/Budget/Manifest/Selection/Compression under Context.
3. Split `context_manifest_runtime.py` by actual behavior.
4. Introduce `MaterializedContextView` and `ContextFingerprint`.
5. Keep memory truth out of Context; expose only a Memory projection retrieval interface.
6. Update `AGENTS.md` bootstrap to canonical new paths, with temporary read-only compatibility fallback if strictly necessary.
7. Add stale `.ai` reference detector; from this phase onward no new `.ai` writes are allowed.

### Exit

New Policy/Context paths are canonical and production bootstrap can operate without writing `.ai`.

## Phase 3 — Runtime / Execution Harness Plane

1. Import Codex runner and `process_runtime.py` into `Runtime/Runner/Codex` and `Runtime/ExecutionControl`.
2. Extract Dispatcher subprocess/tool invocation from Graph `ExecutionOrchestrator` and Ix adapter.
3. Centralize Sandbox, Permissions, Guardrails, Approval enforcement, Mutation enforcement, Verification, EvidenceCapture and Telemetry.
4. Import Unity Editor artifact scanning/export/window functionality under `Runtime/Harnesses/Unity/Editor`.
5. Model Test/Performance/SCM harnesses explicitly.
6. Implement Runtime health contracts for environment/Unity/tool availability.
7. Move hard timeout, hard retry ceiling, turn/cost budget, cancellation, process cleanup and emergency stop into `Runtime/ExecutionControl`.
8. Runner emits typed Runtime failures; it does not grade Agent quality.

### Exit

One Runtime owns actual execution. Graph definitions contain no tool/environment implementation.

## Phase 4 — Orchestration

1. Create explicit `Development Parent Graph`.
2. Model Planning, Investigation, Implementation, Validation and Delivery as first-class SubGraphs.
3. Define Nodes/Edges/Routing/Gates/Parallel/LocalLoops separately.
4. Split semantic continuation/TODO selection from `ContinuationController` into LocalLoops/Routing.
5. Split semantic coordination from `ExecutionOrchestrator` into `Orchestration/Orchestrator`.
6. Add ParentGraph <-> SubGraph state-schema mappings.
7. Add health-check Nodes that call Runtime health contracts only.
8. Preserve fast path for simple tasks:

```text
Policy -> Context -> Runtime -> Verification -> Result
```

9. Use Orchestrator/Worker decomposition only where it materially helps.

### Exit

Graph topology is inspectable; Local Loop is an edge/cycle, not a peer control plane; no Runtime enforcement is hidden in Graph code.

## Phase 5 — Persistence

1. Establish one authoritative execution-state path.
2. Separate `ExecutionState`, `WorkflowState`, `LoopControlState`, `RunCheckpoint`, `SessionRecord`, `MemoryRecord`, and `EvidenceRecord`.
3. Split LayeredMemoryController:
   - durable memory and promotion -> `Persistence/Memory`
   - retrieval projection -> `Context/Retrieval/Memory`
   - evidence capture -> Runtime
   - evidence truth -> `Persistence/Evidence`
4. Make Evidence append-oriented/immutable-oriented.
5. Add checkpoint schema version + full definition fingerprint.
6. Add migrations/compatible loaders for resumable state.

### Exit

Resume, long-term memory reuse, and evidence audit are distinct and independently testable.

## Phase 6 — Eval Consolidation

1. Move Behavior Eval, Golden Eval, datasets, graders, regression and reports under Eval.
2. Convert Golden to a contract containing expected result, invariants, expected trajectory, forbidden behavior, and evidence requirements.
3. Split failure attribution from Runtime execution.
4. Fold `BehaviorEvalAdapter` into canonical Runtime<->Eval contracts; remove redundant transformation only after parity is proven.
5. Add historical production artifact replay for ARCH/NAMING/MUTATION/EVIDENCE.
6. Exclude `not_observed` infrastructure runs from Agent quality denominator.
7. Eval may emit `ChangeProposal`; it may not alter production definitions.

### Exit

Real production artifacts replay through Eval with no fact loss and correct attribution.

## Phase 7 — Operations

1. Runtime emits trace spans, metrics events, structured logs, audit events.
2. Operations owns observability backends/search/dashboard contracts.
3. Add asynchronous failure detection: retry storms, latency/cost/route/quality drift, incident correlation.
4. Add Incident and Runbook contracts.
5. Add `Operations/RuntimeControl` actions: pause/resume/stop, quarantine, disable route, rollback config, force HITL, switch model, replay checkpoint.
6. Every operational control action passes Policy/Approval and calls Runtime/Orchestration through approved control APIs.
7. Add ChangeManagement/VersionManifest.

### Exit

The operational loop closes without bypassing Policy/Approval.

## Phase 8 — Cutover / destructive Human Gate

**Do not execute automatically.**

After explicit human approval and all earlier exits:

1. verify zero active `.ai` reads/writes/references
2. delete `.ai`
3. delete `Tools/LoopIntegration`, Graph compatibility/handoff adapters and obsolete duplicate validators
4. remove active dependency on `DarumaPPAP/Unity-Graph-Engineering`
5. archive/read-only the Graph repository
6. update docs/CI to one-repo source of truth

### Exit

UnityAgent is the single writable source of truth.

## Phase 9 — Production Re-baseline

Run controlled production cases and artifact replay:

- ARCH
- NAMING
- MUTATION
- EVIDENCE
- full Production Smoke
- historical artifact replay

Baseline only when `runtime_timeout`, `runtime_protocol_failure`, `evaluator_contract_failure`, invalid fixture, and unavailable-evidence attribution defects are understood and not silently counted as Agent regressions.

## Commit strategy

Use phase-scoped commits. Avoid mixed “move + semantic rewrite + delete” commits when possible.

Recommended pattern per responsibility:

```text
1. add canonical contract/tests
2. add new implementation behind contract
3. replay existing artifacts
4. switch canonical reference/bootstrap
5. run regression/smoke
6. remove compatibility only at approved cutover
```

History-preserving moves are preferred inside UnityAgent. For Graph-repo imports, migration docs record original repository/path/base revision even when exact Git history transfer is impractical.

## Test matrix by phase

| Phase | Required minimum |
|---|---|
| 0 | document consistency + path/provenance review |
| 1 | unit/contract + historical artifact normalization/replay |
| 2 | Policy equivalence, Context reproducibility/budget, bootstrap stale-ref checks |
| 3 | runner/dispatcher/harness integration, timeout/crash/permission/mutation/evidence tests, production artifact replay |
| 4 | graph topology/state mapping, semantic-loop vs Runtime-retry boundary tests |
| 5 | checkpoint/resume migration, evidence immutability, memory projection/promotion tests |
| 6 | Golden/Behavior regression, attribution denominator, ARCH/NAMING/MUTATION/EVIDENCE replay |
| 7 | observability/control authorization and rollback/replay tests |
| 8 | stale `.ai` + dual-source + compatibility absence checks, full CI |
| 9 | controlled Production Smoke + re-baseline |

## Stop conditions

Stop for human review if any of the following occurs:

- one file/function would have two authoritative owners after the planned split
- a user policy would be deleted, weakened, or silently reworded
- mutation/approval/destructive boundary changes
- state source of truth becomes ambiguous
- Eval would directly modify production definitions
- Golden expectations would enter production Runtime prompt/context
- old and new repositories remain writable sources of truth after proposed cutover
- canonical evidence would be replaced by lossy parsing
- unexplained Production Smoke regression appears
- saved checkpoint definition versions cannot be safely compared/migrated

## Definition of Done

The migration is complete only after `.ai` is gone, Graph repo is no longer an active dependency, UnityAgent is the single source of truth, ParentGraph/SubGraph/Node/Gate/LocalLoop and state mappings are explicit, semantic retry is distinct from Runtime retry, Context is a materialized view, Persistence is authoritative, Checkpoint/Memory/Evidence are distinct, Runtime owns execution enforcement, Operations control is distinct from Runtime safety control, Eval only proposes, all resumable/evaluable contracts are versioned/fingerprinted, artifact replay runs in CI, and Production Smoke is re-baselined with correct failure attribution.
