# Architecture v3.1 Canonical Contracts Proposal

Status: Phase 0 proposal. Concrete schemas are implemented in Phase 1.

## Principles

1. One boundary fact has one canonical structured representation.
2. Authority and enforcement are separate.
3. Resumable/evaluable artifacts carry `schema_version` and definition revisions.
4. Evidence is append-oriented and provenance-bound.
5. Eval consumes Runtime/Persistence facts rather than creating a second execution truth.
6. Infrastructure failures are `not_observed` for Agent-quality scoring.

## DefinitionFingerprint

Persist the deployed combination in Run, Checkpoint, Evidence and Eval artifacts:

```yaml
architecture_version: v3.1
policy_revision: "..."
prompt_revision: "..."
context_revision: "..."
graph_revision: "..."
runtime_profile_revision: "..."
tool_schema_revision: "..."
checkpoint_schema_revision: "..."
evidence_schema_revision: "..."
eval_contract_revision: "..."
```

## Runtime contracts

### ExecutionResult

Required fields:

- `schema_version`, `run_id`, `step_id`, `action_id`
- `status: passed|failed|unavailable|cancelled`
- `started_at`, `completed_at`, `exit_code`
- `runtime_failure`
- canonical `changed_paths`
- `evidence_refs`, `telemetry_refs`
- `definition_fingerprint`

If Runtime observed `changed_paths`, downstream modules must not reconstruct it from a text diff.

### ExecutionEvidence

Required fields:

- `run_id`, `step_id`, `producer`
- `source_type`, `source_ref`
- `status: passed|failed|unavailable`
- `payload_ref`, `hash`, `timestamp`, `provenance`
- `definition_fingerprint`

### MutationEvidence

Required fields:

- `mutation_id`, `run_id`, `step_id`
- `allowed_paths`, `prohibited_paths`, canonical `changed_paths`
- `diff_ref`, `before_fingerprint`, `after_fingerprint`
- `scope_status`, `verification_refs`

Mutation with `changed_paths: []` is an observed no-op fact. Analysis/verification with non-empty `changed_paths` is a mutation-boundary violation.

### RuntimeFailure

Runtime execution failures are emitted as typed facts, including:

- `runtime_timeout`
- `runtime_protocol_failure`
- `unavailable_required_evidence`
- `task_fixture_invalid` when detected at the execution boundary

The Runtime contract also carries `reason`, `retryable`, `source_ref`, and `observation_state`.

## Persistence contracts

### EvidenceRecord

Minimum:

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
definition_fingerprint
```

Evidence is immutable/append-oriented. Memory promotion references Evidence and never overwrites it.

### Explicit state scopes

- `ExecutionState`: current tool/step transient execution truth.
- `WorkflowState`: ParentGraph/SubGraph shared run data.
- `LoopControlState`: semantic-loop attempt/progress only.
- `RunCheckpoint`: durable pause/resume snapshot with definition fingerprint.
- `SessionRecord`: session continuity.
- `MemoryRecord`: reusable cross-session knowledge with source Evidence refs.

Hard timeout/retry ceilings do not belong in `LoopControlState`; they belong in Runtime/ExecutionControl.

## Context contracts

### MaterializedContextView

Contains only the current-call projection:

- `context_id`, `run_id`
- prompt specification reference
- selected policy/context/repository/memory-projection/tool-schema refs
- unresolved bindings
- budget report ref
- context fingerprint and definition fingerprint

It is not authoritative WorkflowState, Memory, Checkpoint, or Evidence.

### MemoryProjection

A bounded projection references `memory_id` and source evidence. Context never becomes the durable Memory store.

## Orchestration contracts

### ParentGraphDefinition / SubGraphDefinition

The default Development Parent Graph contains Planning, Investigation, Implementation, Validation and Delivery SubGraphs, while preserving a simple-task fast path.

Every SubGraph has explicit:

- input/output state mapping
- Nodes and Edges
- Gate placement
- Local semantic loops

### ExecutionAction

Contains `action_id`, `run_id`, `node_id`, `action_type`, `payload_ref`, Policy requirement refs and verification requirement refs. It says **what** should execute, not **how** process/tool enforcement works.

### ExecutionTicket

References the selected action, graph revision and workflow-state revision. Runtime validates the ticket against the current Runtime profile and Policy requirements before execution.

## Approval contracts

The boundary is deliberately split:

```text
Policy/ApprovalRequirement
 -> Orchestration/GatePlacement
 -> Runtime/ApprovalDecision + checkpoint/resume enforcement
```

Policy defines whether approval is required. Graph places the stop. Runtime performs pause, serialization, decision handling and resume/replan/stop.

## Runtime health contract

Runtime owns health implementations and returns a structured result with:

- `check_id`
- `kind: environment|unity_availability|tool_health`
- `status: healthy|degraded|unavailable|failed`
- `observed_at`
- `evidence_refs`
- bounded details

Orchestration HealthCheck Nodes only call this contract.

## Eval contracts

### GoldenContract

```yaml
expected_result: []
invariants: []
expected_trajectory: []
forbidden: []
evidence_requirements: []
contract_revision: "..."
```

Golden content is Eval-only and must not be injected into a production Runtime prompt as hidden expected-answer guidance.

### AttributionResult

Required fields:

- `run_id`
- `observation_state: observed|not_observed`
- `failure_class`
- `quality_denominator_eligible`
- `runtime_failure_ref`
- `evidence_refs`
- `reason`

Minimum failure classes:

- `agent_behavior_regression`
- `runtime_timeout`
- `runtime_protocol_failure`
- `evaluator_contract_failure`
- `task_fixture_invalid`
- `unavailable_required_evidence`

Infrastructure/evaluator/fixture/unavailable-required-evidence outcomes are not Agent-quality observations.

## Eval deployment boundary

The only supported path from Eval feedback to production is:

```text
Attribution
 -> Report
 -> Change Proposal
 -> Regression/Safety
 -> Approval
 -> Operations/ChangeManagement
 -> Versioned Deploy
```

No direct `Eval -> Policy/Context/Orchestration/Runtime` write contract is created.

## Migration compatibility rule

Temporary adapters may convert legacy bundles only until canonical contracts are native end-to-end. They must preserve raw refs/hashes, prefer existing structured legacy facts such as `metrics.json.changed_paths`, fail closed on contradiction, never synthesize PASS for an unobserved gate, and be deleted after cutover.
