# Operations Migration

Status: implementation branch  
Branch: `refactor/architecture-phase7-operations`  
Base: `cbbfb59c5877e43aec4a019aeeb911dd167455f0`

## Goal

Close the operational loop without moving execution authority out of Runtime, semantic authority out of Orchestration, durable execution/evidence truth out of Persistence, or quality attribution out of Eval.

```text
Runtime / Eval structured facts
        ↓
Operations Observability
        ↓
Asynchronous Detection
        ↓
Incident + Runbook
        ↓
RuntimeControl Request
        ↓
Policy Decision
        ↓
Approval Decision
        ↓
Approved Control Command
        ↓
Runtime / Orchestration / ChangeManagement approved API
```

## Canonical Operations ownership

```text
Operations/
├─ Observability/
│  ├─ TraceRecord
│  ├─ MetricEvent
│  ├─ StructuredLogEvent
│  ├─ AuditEvent
│  ├─ event_store.py
│  ├─ backend-contract.yaml
│  └─ dashboard-contract.yaml
├─ Detection/
│  ├─ detection-event.schema.yaml
│  ├─ detection-policy.yaml
│  └─ detector.py
├─ Incidents/
│  ├─ incident.schema.yaml
│  ├─ runbook.schema.yaml
│  ├─ runbooks.yaml
│  └─ incident_manager.py
├─ RuntimeControl/
│  ├─ runtime-control-request.schema.yaml
│  ├─ approved-control-command.schema.yaml
│  ├─ action-catalog.yaml
│  └─ control_gateway.py
├─ ChangeManagement/
│  ├─ version-manifest.schema.yaml
│  ├─ change-request.schema.yaml
│  ├─ change_manager.py
│  └─ operations_api.py
└─ Tests/
```

## Runtime telemetry boundary

Runtime remains the producer of execution telemetry. `Runtime/Telemetry/runtime_telemetry.py` emits contract-compatible trace spans, metrics, structured logs and audit events. Operations owns ingestion/search/dashboard/detection, not the production execution itself.

Telemetry may reference durable Evidence IDs but never becomes the canonical Evidence truth. That remains `Persistence/Evidence`.

## RuntimeControl boundary

`Operations/RuntimeControl` is external operational control and is not `Runtime/ExecutionControl`.

Supported Phase-7 actions:

- pause
- resume
- stop
- quarantine
- disable route
- rollback config
- force HITL
- switch model
- replay checkpoint

Raw requests cannot be dispatched. An action becomes dispatchable only after:

1. canonical action-catalog validation;
2. Policy decision says the action is allowed;
3. Policy-selected risk is not below the action minimum;
4. Policy explicitly decides whether approval is required;
5. Approval outcome is `approved` when required, otherwise `not_required` or an explicit approval;
6. an authorization hash binds the approved command contents;
7. dispatch uses only the target authority's approved operational API.

R4 `always_required` approval is checked against `Policy/Approval/approval-policy.yaml` and cannot be downgraded by Operations.

## Approved authority APIs

- `Runtime/Control/operations_api.py`: pause/resume/stop/quarantine/switch-model handoff only;
- `Orchestration/Control/operations_api.py`: disable-route/force-HITL/replay-checkpoint semantic handoff only;
- `Operations/ChangeManagement/operations_api.py`: approved rollback/config control only.

Operations never imports or calls `Runtime/ExecutionControl` internals. Runtime still owns timeout, hard retry ceiling, cancellation, process cleanup and emergency execution safety.

Checkpoint replay requires both a checkpoint ID and a `Persistence/Resume` compatibility decision reference before the approved Orchestration API accepts the command.

## Detection and incidents

Phase 7 detects:

- retry storms;
- latency drift;
- cost drift;
- route drift;
- quality drift sourced from Eval-eligible observations;
- correlated incidents when multiple signal kinds affect the same run.

`not_observed` Eval records remain outside quality drift denominator because `quality_denominator_eligible=false` records are ignored.

Detection never mutates Runtime or Eval. It creates operational DetectionEvents, which may be correlated into Incident records and associated with explicit Runbooks.

Runbook control steps declare `requires_human_gate: true` and still go through the same Policy/Approval control gateway.

## ChangeManagement / VersionManifest

`VersionManifest` extends the canonical DefinitionFingerprint revisions with `operations_revision` so rollout/rollback decisions can identify the exact operational configuration.

ChangeRequests start as `proposed`. They may only transition to `authorized` after Policy/Approval decisions are supplied, and may only be applied through an injected ChangeManagement deployment port.

Eval ChangeProposals remain proposals. They do not bypass Policy/Approval or directly modify production definitions.

## Observability backend contract

Operations owns append-oriented operational telemetry/search/dashboard contracts. This does not replace:

- Persistence ExecutionState / WorkflowState / LoopControlState;
- Persistence Evidence truth;
- Eval quality attribution;
- Runtime execution state/control internals.

Dashboards and search are read-only surfaces.

## Validation

`Validate Operations` covers:

- all four Runtime observability event contracts;
- append/query/search backend behavior;
- retry/latency/cost/route/quality detection;
- `not_observed` denominator exclusion;
- incident/runbook schemas and transitions;
- Policy denial and missing approval fail-closed behavior;
- authorization-tamper rejection;
- Runtime / Orchestration / ChangeManagement approved control APIs;
- checkpoint replay Resume decision requirement;
- R4 rollback approval requirement;
- VersionManifest and approval-gated change application;
- no Operations dependency on Runtime ExecutionControl internals;
- previous Runtime/Orchestration/Persistence/Eval tests and `Tools/validate_all.py`.

## Non-goals / later Human Gates

Phase 7 does not:

- delete `.ai`;
- delete compatibility shims;
- archive `Unity-Graph-Engineering`;
- re-baseline Production Smoke;
- allow Eval to apply its own ChangeProposal;
- move hard runtime safety controls into Operations;
- perform destructive cutover.

Those remain Phase 8/9 gates.

## Exit criteria

Phase 7 is complete when:

1. Runtime emits structured trace/metric/log/audit records;
2. Operations can ingest/search those records without becoming Evidence or execution-state truth;
3. asynchronous detection produces typed operational signals;
4. Incident and Runbook contracts are validated;
5. all control actions fail closed without Policy/Approval provenance;
6. approved commands dispatch only through explicit authority control APIs;
7. rollback and replay cannot bypass approval or Resume compatibility;
8. VersionManifest and ChangeManagement are tested;
9. Phase 7 CI plus all earlier authority boundary tests are green.
