# Architecture v3.1 Dependency Map

Status: Phase 0  
Architecture rule: **Policy defines / Context materializes / Orchestration decides / Runtime executes / Persistence remembers / Operations observes and controls / eval measures and proposes**.

## Canonical dependency direction

```text
                         ┌──────────── src/unityagent/policy ─────────────┐
                         │ constrains every plane         │
                         ▼                                ▼
src/unityagent/persistence/external ─> src/unityagent/context ─> src/unityagent/orchestration ─> src/unityagent/runtime
      ▲                    │              │             │
      │                    │              │             ├─> src/unityagent/persistence/evidence
      │                    │              │             ├─> src/unityagent/persistence/state
      │                    │              │             └─> Runtime Telemetry
      │                    │              │                         │
      │                    │              │                         ▼
      │                    │              │                    src/unityagent/operations
      │                    │              │                         │
      │                    │              └<── approved control ────┘
      │                    │
      │                    └─ current-call projection only
      │
      └──────────────── source of truth

src/unityagent/runtime/persistence artifacts ─> eval ─> Attribution ─> Report
                                      └─> Change Proposal
                                            └─> Regression/Safety
                                                  └─> Approval
                                                        └─> src/unityagent/operations/change_management
                                                              └─> Versioned Deploy
```

## Module dependency contract

Legend: `R` = may read/call the public contract; `W` = may be the authoritative writer; `-` = no direct authority dependency.

| From \ To | src/unityagent/policy | src/unityagent/context | src/unityagent/orchestration | src/unityagent/runtime | src/unityagent/persistence | src/unityagent/operations | eval |
|---|---:|---:|---:|---:|---:|---:|---:|
| src/unityagent/policy | W | - | - | - | - | - | - |
| src/unityagent/context | R | W | - | R facts only | R projection sources | - | - |
| src/unityagent/orchestration | R | R materialized view | W | R execution contracts | R state projection | R approved status only | - |
| src/unityagent/runtime | R | R execution input | R selected action | W | W through Persistence APIs/contracts | emits telemetry | - |
| src/unityagent/persistence | R retention/security clauses | - | - | - | W | R operational metadata | - |
| src/unityagent/operations | R | - | R via approved control API | R via approved enforcement API | R checkpoints/audit | W | R reports only |
| eval | R compliance clauses | R versioned context artifacts | R trajectory artifacts | R typed execution/evidence | R evidence/replay artifacts | - | W |

`W through Persistence APIs/contracts` means Runtime may create evidence/state/checkpoint records, but the durable truth and schema ownership remain Persistence.

## Required public boundaries

### src/unityagent/policy -> consumers

- `PolicyClauseSet`
- `ApprovalRequirement`
- `EvidenceRequirement`
- `RiskLevel`
- `PermissionPolicy`
- immutable/versioned revision identifiers

Policy never invokes tools and never schedules graph nodes.

### src/unityagent/context -> model/runtime request

- `ContextManifest`
- `MaterializedContextView`
- `PromptSpecification`
- `ContextFingerprint`

Context may read durable memory through a projection interface; it never writes Memory as part of context assembly.

### src/unityagent/orchestration -> src/unityagent/runtime

- `ExecutionAction`
- `ExecutionTicket`
- `GateRequirementRef`
- `RuntimeHealthQuery`
- `SubGraphStateProjection`

Orchestration chooses the action. Runtime decides whether that action can be safely executed under current permissions, budgets, timeout/cancellation, and environment health.

### src/unityagent/runtime -> Persistence / eval

- `ExecutionResult`
- `ExecutionEvidence`
- `MutationEvidence`
- `RuntimeFailure`
- `TelemetryEvent`
- `CheckpointWriteRequest`

The same canonical structured facts must cross src/unityagent/runtime -> src/unityagent/persistence -> eval without lossy re-parsing.

### src/unityagent/persistence -> Context / Orchestration / Operations / eval

- `ExecutionState`
- `WorkflowState`
- `LoopControlState`
- `RunCheckpoint`
- `SessionRecord`
- `MemoryRecord`
- `EvidenceRecord`

These records have explicit scope and version/provenance.

### src/unityagent/operations -> Runtime / src/unityagent/orchestration

Only after src/unityagent/policy/approval:

- pause/resume/stop run
- quarantine tool
- disable route
- rollback configuration
- reduce budget
- force HITL
- switch model
- replay from checkpoint

Operations cannot mutate production definitions directly from an eval score.

### eval -> Change Management

- `AttributionResult`
- `EvalReport`
- `ChangeProposal`

No direct write API from eval to src/unityagent/policy/context/orchestration/runtime/persistence definitions is allowed.

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
│  ├─ Mutation intent/route is src/unityagent/orchestration
│  ├─ Mutation permission + execution is src/unityagent/runtime
│  └─ changed_paths/diff/build output become canonical Evidence
│
├─ Validation SubGraph
│  ├─ selects required tests/regression/benchmark/visual Verification
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
| Semantic Recovery | src/unityagent/orchestration | new hypothesis, re-investigate, alternative implementation, replan | process timeout, kill, hard retry ceiling |
| Execution Recovery | src/unityagent/runtime | transient tool retry, process crash cleanup, timeout, cancellation | semantic task replanning |
| Operational Recovery | src/unityagent/operations | quarantine, rollback, force HITL, approved checkpoint replay | bypass src/unityagent/policy/approval |

## State-schema ownership

```text
src/unityagent/persistence/state/execution_state
  └─ current tool/step transient execution truth
src/unityagent/persistence/state/workflow_state
  └─ ParentGraph/SubGraph shared run data
src/unityagent/persistence/state/loop_control_state
  └─ semantic-loop progress/attempt metadata
src/unityagent/persistence/checkpoints/run_checkpoint
  └─ durable pause/resume snapshot
src/unityagent/persistence/sessions/session_record
  └─ session continuity
src/unityagent/persistence/memory/memory_record
  └─ reusable cross-session knowledge
src/unityagent/persistence/evidence/evidence_record
  └─ factual provenance-bound record

src/unityagent/orchestration/graph/state_mapping/
  └─ maps Graph/SubGraph inputs/outputs to the Persistence-owned schemas;
     it does not become another authoritative state store.
```

## Runtime / Execution Harness Plane

```text
src/unityagent/runtime/
├─ Runner/Codex/
├─ Dispatcher/
├─ Harnesses/
│  ├─ Unity/{Editor,BatchMode,BuildPipeline,Player}/
│  ├─ tests/{EditMode,PlayMode}/
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
2. `tools/ContextManifest/context_manifest_runtime.py` loads src/unityagent/context, Graph, User src/unityagent/policy, Quality Gates, Risk and MCP activation directly. This creates a broad cross-authority dependency and must be split.
3. Graph `ExecutionOrchestrator` directly invokes Continuation, Memory and Ix controllers and performs timeout/path/scope enforcement. Semantic orchestration and Runtime dispatch are currently coupled.
4. Graph `LayeredMemoryController` captures raw evidence and manages memory under the same controller. Persistence ownership must be separated by record type.
5. Graph `CodexProductionAgent` executes the model but also aggregates quality gates and classifies some failures. Runtime facts and eval attribution must cross a typed boundary.
6. `BehaviorEvalAdapter` is currently needed because Runtime and eval contracts are not identical. It becomes removable only after canonical contracts are used end-to-end.
7. Root `tools/`, root `.ai/`, Graph root `policies/` and root `schemas/` hide responsibility ownership. New modules place contracts/validators/tests next to their owner.

## Forbidden dependency checks to add to CI

- `src/unityagent/policy/**` importing/invoking src/unityagent/runtime, tool, subprocess, Unity, Git, or eval execution code.
- `src/unityagent/context/**` writing durable Memory/Checkpoint/Evidence truth.
- `src/unityagent/orchestration/**` implementing permission enforcement, process timeout/kill, hard retry ceilings, or environment health implementations.
- `src/unityagent/runtime/**` defining user/organization policy or grading Golden expected outcomes.
- `src/unityagent/persistence/**` using Context Manifest as the authoritative resume source.
- `src/unityagent/operations/**` applying control changes without src/unityagent/policy/approval authorization.
- `eval/**` writing production definitions or importing production prompt expected-answer fixtures.
- any post-cutover reference to `.ai/` or active `Unity-Graph-Engineering` runtime paths.
- any adapter that re-parses text/diff to recover a fact already present in canonical Runtime evidence.

## Migration order constraints

```text
Phase 0 Contract + inventory
   ↓
Phase 1 Canonical boundary contracts
   ↓
Phase 2 src/unityagent/policy + src/unityagent/context
   ↓
Phase 3 src/unityagent/runtime/harness
   ↓
Phase 4 src/unityagent/orchestration
   ↓
Phase 5 src/unityagent/persistence
   ↓
Phase 6 eval + Replay
   ↓
Phase 7 src/unityagent/operations
   ↓
Human Gate
   ↓
Phase 8 .ai removal / compatibility deletion / Graph repo archive
   ↓
Phase 9 Production re-baseline
```

No later phase may silently redefine an earlier phase's authority contract. Boundary changes require contract tests plus production artifact replay.
