# Architecture v3.1 Dependency Map

Status: Phase 0  
Architecture rule: **Policy defines / Context materializes / Orchestration decides / Runtime executes / Persistence remembers / Operations observes and controls / Eval measures and proposes**.

## Canonical dependency direction

```text
                         ┌──────────── Policy ─────────────┐
                         │ constrains every plane         │
                         ▼                                ▼
Persistence/External ─> Context ─> Orchestration ─> Runtime
      ▲                    │              │             │
      │                    │              │             ├─> Persistence/Evidence
      │                    │              │             ├─> Persistence/State
      │                    │              │             └─> Runtime Telemetry
      │                    │              │                         │
      │                    │              │                         ▼
      │                    │              │                    Operations
      │                    │              │                         │
      │                    │              └<── approved control ────┘
      │                    │
      │                    └─ current-call projection only
      │
      └──────────────── source of truth

Runtime/Persistence artifacts ─> Eval ─> Attribution ─> Report
                                      └─> Change Proposal
                                            └─> Regression/Safety
                                                  └─> Approval
                                                        └─> Operations/ChangeManagement
                                                              └─> Versioned Deploy
```

## Module dependency contract

Legend: `R` = may read/call the public contract; `W` = may be the authoritative writer; `-` = no direct authority dependency.

| From \ To | Policy | Context | Orchestration | Runtime | Persistence | Operations | Eval |
|---|---:|---:|---:|---:|---:|---:|---:|
| Policy | W | - | - | - | - | - | - |
| Context | R | W | - | R facts only | R projection sources | - | - |
| Orchestration | R | R materialized view | W | R execution contracts | R state projection | R approved status only | - |
| Runtime | R | R execution input | R selected action | W | W through Persistence APIs/contracts | emits telemetry | - |
| Persistence | R retention/security clauses | - | - | - | W | R operational metadata | - |
| Operations | R | - | R via approved control API | R via approved enforcement API | R checkpoints/audit | W | R reports only |
| Eval | R compliance clauses | R versioned context artifacts | R trajectory artifacts | R typed execution/evidence | R evidence/replay artifacts | - | W |

`W through Persistence APIs/contracts` means Runtime may create evidence/state/checkpoint records, but the durable truth and schema ownership remain Persistence.

## Required public boundaries

### Policy -> consumers

- `PolicyClauseSet`
- `ApprovalRequirement`
- `EvidenceRequirement`
- `RiskLevel`
- `PermissionPolicy`
- immutable/versioned revision identifiers

Policy never invokes tools and never schedules graph nodes.

### Context -> model/runtime request

- `ContextManifest`
- `MaterializedContextView`
- `PromptSpecification`
- `ContextFingerprint`

Context may read durable memory through a projection interface; it never writes Memory as part of context assembly.

### Orchestration -> Runtime

- `ExecutionAction`
- `ExecutionTicket`
- `GateRequirementRef`
- `RuntimeHealthQuery`
- `SubGraphStateProjection`

Orchestration chooses the action. Runtime decides whether that action can be safely executed under current permissions, budgets, timeout/cancellation, and environment health.

### Runtime -> Persistence / Eval

- `ExecutionResult`
- `ExecutionEvidence`
- `MutationEvidence`
- `RuntimeFailure`
- `TelemetryEvent`
- `CheckpointWriteRequest`

The same canonical structured facts must cross Runtime -> Persistence -> Eval without lossy re-parsing.

### Persistence -> Context / Orchestration / Operations / Eval

- `ExecutionState`
- `WorkflowState`
- `LoopControlState`
- `RunCheckpoint`
- `SessionRecord`
- `MemoryRecord`
- `EvidenceRecord`

These records have explicit scope and version/provenance.

### Operations -> Runtime / Orchestration

Only after Policy/Approval:

- pause/resume/stop run
- quarantine tool
- disable route
- rollback configuration
- reduce budget
- force HITL
- switch model
- replay from checkpoint

Operations cannot mutate production definitions directly from an Eval score.

### Eval -> Change Management

- `AttributionResult`
- `EvalReport`
- `ChangeProposal`

No direct write API from Eval to Policy/Context/Orchestration/Runtime/Persistence definitions is allowed.

## Parent Graph dependency map

```text
Development Parent Graph
│
├─ Planning SubGraph
│  ├─ reads ContextManifest
│  ├─ may call Runtime health contracts through HealthCheck Nodes
│  └─ emits WorkflowState projection
│
├─ Investigation SubGraph
│  ├─ Code/Asset/Log/Profiler analysis Nodes
│  ├─ Runtime Harness calls execute the actual Unity/Ix/Test/Profiler operations
│  └─ Evidence Gate may loop semantically to New Hypothesis
│
├─ Implementation SubGraph
│  ├─ Mutation intent/route is Orchestration
│  ├─ Mutation permission + execution is Runtime
│  └─ changed_paths/diff/build output become canonical Evidence
│
├─ Validation SubGraph
│  ├─ selects required Tests/Regression/Benchmark/Visual Verification
│  └─ Runtime Harness performs them and emits Evidence
│
└─ Delivery SubGraph
   ├─ selects documentation/commit/PR/report actions
   └─ Runtime SCM Harness executes Git/GitHub actions
```

Local semantic loops are edges/cycles inside the owning graph/subgraph. They are not a separate top-level controller.

## Recovery dependency map

| Recovery type | Owner | Examples | Must not own |
|---|---|---|---|
| Semantic Recovery | Orchestration | new hypothesis, re-investigate, alternative implementation, replan | process timeout, kill, hard retry ceiling |
| Execution Recovery | Runtime | transient tool retry, process crash cleanup, timeout, cancellation | semantic task replanning |
| Operational Recovery | Operations | quarantine, rollback, force HITL, approved checkpoint replay | bypass Policy/Approval |

## State-schema ownership

```text
Persistence/State/ExecutionState
  └─ current tool/step transient execution truth
Persistence/State/WorkflowState
  └─ ParentGraph/SubGraph shared run data
Persistence/State/LoopControlState
  └─ semantic-loop progress/attempt metadata
Persistence/Checkpoints/RunCheckpoint
  └─ durable pause/resume snapshot
Persistence/Sessions/SessionRecord
  └─ session continuity
Persistence/Memory/MemoryRecord
  └─ reusable cross-session knowledge
Persistence/Evidence/EvidenceRecord
  └─ factual provenance-bound record

Orchestration/Graph/StateMapping/
  └─ maps Graph/SubGraph inputs/outputs to the Persistence-owned schemas;
     it does not become another authoritative state store.
```

## Runtime / Execution Harness Plane

```text
Runtime/
├─ Runner/Codex/
├─ Dispatcher/
├─ Harnesses/
│  ├─ Unity/{Editor,BatchMode,BuildPipeline,Player}/
│  ├─ Tests/{EditMode,PlayMode}/
│  ├─ Performance/{Profiler,MemoryProfiler,Benchmark}/
│  └─ SCM/{Git,GitHub}/
├─ Sandbox/
├─ Permissions/
├─ Guardrails/
├─ Approval/
├─ Mutation/
├─ Verification/
├─ EvidenceCapture/
├─ Telemetry/
├─ ExecutionControl/
└─ Health/
```

The current Unity Artifact Graph scanner belongs to the Unity Editor Harness for execution because it calls `UnityEditor.AssetDatabase`. Its dependency graph output is repository/context evidence; it is not the agent-control Parent Graph.

## Current dependency violations / migration seams

1. `UnityAgent/AGENTS.md` currently delegates Production execution, Loop/Graph/Retry/Checkpoint/Human Gate to a second writable repo. Phase 8 removes this two-source runtime relationship.
2. `Tools/ContextManifest/context_manifest_runtime.py` loads Context, Graph, User Policy, Quality Gates, Risk and MCP activation directly. This creates a broad cross-authority dependency and must be split.
3. Graph `ExecutionOrchestrator` directly invokes Continuation, Memory and Ix controllers and performs timeout/path/scope enforcement. Semantic orchestration and Runtime dispatch are currently coupled.
4. Graph `LayeredMemoryController` captures raw evidence and manages memory under the same controller. Persistence ownership must be separated by record type.
5. Graph `CodexProductionAgent` executes the model but also aggregates quality gates and classifies some failures. Runtime facts and Eval attribution must cross a typed boundary.
6. `BehaviorEvalAdapter` is currently needed because Runtime and Eval contracts are not identical. It becomes removable only after canonical contracts are used end-to-end.
7. Root `Tools/`, root `.ai/`, Graph root `policies/` and root `schemas/` hide responsibility ownership. New modules place contracts/validators/tests next to their owner.

## Forbidden dependency checks to add to CI

- `Policy/**` importing/invoking Runtime, tool, subprocess, Unity, Git, or Eval execution code.
- `Context/**` writing durable Memory/Checkpoint/Evidence truth.
- `Orchestration/**` implementing permission enforcement, process timeout/kill, hard retry ceilings, or environment health implementations.
- `Runtime/**` defining user/organization policy or grading Golden expected outcomes.
- `Persistence/**` using Context Manifest as the authoritative resume source.
- `Operations/**` applying control changes without Policy/Approval authorization.
- `Eval/**` writing production definitions or importing production prompt expected-answer fixtures.
- any post-cutover reference to `.ai/` or active `Unity-Graph-Engineering` runtime paths.
- any adapter that re-parses text/diff to recover a fact already present in canonical Runtime evidence.

## Migration order constraints

```text
Phase 0 Contract + inventory
   ↓
Phase 1 Canonical boundary contracts
   ↓
Phase 2 Policy + Context
   ↓
Phase 3 Runtime/Harness
   ↓
Phase 4 Orchestration
   ↓
Phase 5 Persistence
   ↓
Phase 6 Eval + Replay
   ↓
Phase 7 Operations
   ↓
Human Gate
   ↓
Phase 8 .ai removal / compatibility deletion / Graph repo archive
   ↓
Phase 9 Production re-baseline
```

No later phase may silently redefine an earlier phase's authority contract. Boundary changes require contract tests plus production artifact replay.
