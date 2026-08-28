# UnityAgent Architecture v3.1

Status: **Architecture Contract / Phase 0 Freeze**

## Canonical repository

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

Final source of truth is `DarumaPPAP/UnityAgent`. `.ai/` is a migration source only and is deleted only after approved cutover. `DarumaPPAP/Unity-Graph-Engineering` becomes archive/read-only only after successful import, one-repo Production Smoke, and explicit human approval.

Do not create top-level `Core/`, `Common/`, `Shared/`, `Tools/`, or `Schemas/` as responsibility catch-alls. Contracts, validators and tests live close to their owner.

## Authority contract

```text
Policy defines
Context materializes model input
Orchestration decides
Runtime executes
Persistence remembers
Operations observes and controls
Eval measures and proposes
```

### Policy

Owns user/security/approval/evidence/risk rules. Does not own execution state, tool calls, graph scheduling, or grading.

### Context

Owns Prompt specification, retrieval, packs, selection, compression, budget, bounded Memory projection, manifest and final current-call assembly. Context is a **Materialized Context View**, never the durable state or Memory source of truth.

### Orchestration

Owns ParentGraph, SubGraph, Node/Edge, Routing, Branch/Join, Parallel, Gate placement, Local semantic loops, semantic replan and justified orchestrator-worker decomposition.

```text
Parent Graph
  -> SubGraph
      -> Node / Edge / Gate
          -> Local Loop when needed
```

A giant independent Loop Controller beside Graph is forbidden.

### Runtime / Execution Harness Plane

Owns actual execution: model runner, dispatcher, Unity/Test/Performance/SCM harnesses, sandbox, permissions, guardrails, HITL enforcement, mutation enforcement, verification, evidence capture, telemetry and hard execution safety.

```text
Runtime/Harnesses/
├─ Unity/
├─ Tests/
├─ Performance/
└─ SCM/
```

`Runtime/ExecutionControl` owns max turns, hard retry ceiling, timeout, cost ceiling, cancellation, crash cleanup/recovery and emergency stop.

Runtime owns health implementations. Orchestration may own only `EnvironmentCheck`, `UnityAvailabilityCheck` and `ToolHealthCheck` Nodes that call Runtime health contracts.

### Persistence

Owns authoritative `ExecutionState`, `WorkflowState`, `LoopControlState`, `RunCheckpoint`, `SessionRecord`, long-term `MemoryRecord` and `EvidenceRecord`.

```text
Checkpoint != Memory != Evidence
```

Evidence is append-oriented and provenance-bound. Memory promotion never overwrites Evidence.

### Operations

Owns production observability, asynchronous failure detection, incidents, runbooks, operational runtime control and rollout/rollback/configuration change management.

`Operations/RuntimeControl` is external operational control (pause/resume/stop/quarantine/rollback/force HITL/switch model/replay checkpoint) and is distinct from `Runtime/ExecutionControl`. Operations always passes Policy/Approval.

### Eval

Owns datasets, Golden Contracts, graders/scorers, behavior/regression eval, Production Smoke definitions, artifact replay, attribution, reports and change proposals.

Eval never directly modifies production definitions.

```text
Eval
 -> Attribution
 -> Report
 -> Change Proposal
 -> Regression/Safety
 -> Approval
 -> Operations/ChangeManagement
 -> Versioned Deploy
```

## Recovery ownership

```text
Semantic Recovery    -> Orchestration
Execution Recovery   -> Runtime
Operational Recovery -> Operations
```

Semantic Retry/Replan is different from transient process/tool retry, timeout, crash recovery, or hard retry ceilings.

## Default Development Parent Graph

Reusable topology, not a mandatory sequence:

```text
Development Parent Graph
│
├─ Planning SubGraph
│  ├─ Requirement Analysis
│  ├─ Context Collection
│  ├─ Task Breakdown
│  ├─ Plan
│  └─ Planning Gate
│
├─ Investigation SubGraph
│  ├─ Code Analysis
│  ├─ Asset / Project Analysis
│  ├─ Log / Profiler Analysis
│  ├─ Hypothesis
│  └─ Evidence Gate
│
├─ Implementation SubGraph
│  ├─ Change Planning
│  ├─ Code / Asset Mutation
│  ├─ Build
│  └─ Build Gate
│
├─ Validation SubGraph
│  ├─ Tests
│  ├─ Regression
│  ├─ Benchmark
│  ├─ Visual Verification
│  └─ Quality Gate
│
└─ Delivery SubGraph
   ├─ Documentation
   ├─ Commit / PR
   ├─ Change Summary
   └─ User Report
```

Simple local tasks preserve the fast path:

```text
Policy -> Context -> Runtime -> Verification -> Result
```

## Approval contract

```text
Approval Policy
 -> Approval Requirement
 -> Graph Gate Placement
 -> Runtime Approval Enforcement
 -> approve / edit / reject
 -> resume / replan / stop
```

Policy defines the requirement, Graph chooses the stop point, Runtime enforces pause/serialization/decision/resume.

## Evidence contract

Minimum durable Evidence fields:

```text
evidence_id
run_id
step_id
source_type
source_ref
timestamp
hash
producer
verification_status
provenance
```

Compile/Runtime/Editor/Player/device/Performance/Visual states remain separately evidenced. A canonical structured Runtime fact must not be reconstructed from a weaker text/diff form downstream.

## Evaluation contract

Golden is a contract, not only an expected final string. It supports:

- expected result
- invariants
- expected trajectory
- forbidden behaviors
- evidence requirements

Minimum failure attribution:

- `agent_behavior_regression`
- `runtime_timeout`
- `runtime_protocol_failure`
- `evaluator_contract_failure`
- `task_fixture_invalid`
- `unavailable_required_evidence`

`not_observed` infrastructure/evaluator/fixture runs do not enter the Agent-quality denominator.

## Versioning

Version/fingerprint at minimum:

- Policy
- Prompt
- Context
- ParentGraph/SubGraph
- Runtime execution profile
- tool schemas
- checkpoint schema
- evidence schema
- Eval/Golden/Grader contracts

Run/Checkpoint/Evidence/Eval artifacts retain these revisions. Resume compares saved and current definitions and chooses compatible resume, tested migration, or fail-closed review.

## Production Smoke

```text
Eval/ProductionSmoke
  case / invariants / grader
        ↓
Runtime/Runner/Codex
  real execution/routing/tools/permissions
        ↓
Persistence/Evidence
        ↓
Eval/Graders
```

Destructive effects remain sandboxed/fixture-controlled. Historical ARCH/NAMING/MUTATION/EVIDENCE artifacts are replayed in CI.

## Migration phases

0. Architecture Contract + inventory only.
1. Canonical contracts.
2. Policy + Context.
3. Runtime / Harness import.
4. Orchestration import and explicit SubGraphs.
5. Persistence consolidation.
6. Eval consolidation + artifact replay.
7. Operations closure.
8. Human-approved `.ai` removal, compatibility deletion, Graph-repo cutover/archive.
9. Production Smoke re-baseline.

Each phase runs tests, updates migration documentation, and stops on unexplained failures.

## Protected existing behavior

The migration must preserve the existing authoritative user-specific UnityAgent policy, including minimal cohesive solution first, no premature abstraction/generalization, exact evidence honesty, mutation safety, approval boundaries, existing comment policy, naming policy, and no unrequested implementation.

## Phase 0 companion documents

- `docs/migration/architecture-inventory.md`
- `docs/migration/architecture-dependency-map.md`
- `docs/migration/architecture-migration-plan.md`
- `docs/migration/architecture-canonical-contracts.md`
- `docs/migration/architecture-split-list.md`
- `docs/migration/architecture-compatibility-delete-list.md`
- `docs/migration/architecture-version-resume-matrix.md`
- `docs/migration/architecture-harness-health-contract.md`

These documents are the review gate before broad movement.
