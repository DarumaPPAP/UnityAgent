# Architecture v3.1 Harness Health-Check Node Contract

Status: Phase 0.

## Boundary

Runtime owns the actual environment/tool/Unity health implementations. Orchestration may own graph Nodes that request those Runtime contracts.

```text
src/unityagent/orchestration/graph/health_checks/
├─ EnvironmentCheck/
├─ UnityAvailabilityCheck/
└─ ToolHealthCheck/
          │
          │ request only
          ▼
src/unityagent/runtime/health/
├─ EnvironmentHealthProbe
├─ UnityHealthProbe
└─ ToolHealthProbe
          │
          ▼
src/unityagent/runtime/contracts/health_check_result
          │
          ├─> Orchestration Gate/Route decision
          ├─> Runtime Telemetry
          └─> Persistence Evidence when required
```

Graph Nodes must not call OS process APIs, Unity Editor APIs, tool binaries, network transports, or SCM directly to determine health.

## Runtime HealthCheckResult

Minimum contract:

```yaml
schema_version: "1.0"
check_id: "..."
run_id: "..."
step_id: "..."
kind: environment | unity_availability | tool_health
target: "..."
status: healthy | degraded | unavailable | failed
observed_at: "..."
evidence_refs: []
details: {}
runtime_profile_revision: "..."
tool_schema_revision: "..."
```

Rules:

- `details` is diagnostic metadata, not a replacement for required Evidence.
- Runtime may return `unavailable` without converting it to success/failure for Eval.
- Health probes obey Runtime timeout/cancellation and permission enforcement.
- A health probe is read-only unless a separate approved repair action exists.
- Repair is never implicit in a check.

## EnvironmentCheck Node

Purpose: decide whether the selected graph path has enough healthy Runtime environment capability to continue.

Request examples:

- workspace exists/is accessible
- required executable/runtime capability is available
- required fixture/source exists
- sandbox can be established

Node behavior:

```text
request Runtime EnvironmentHealthProbe
  ├─ healthy  -> continue
  ├─ degraded -> route according to task evidence requirement
  ├─ unavailable -> mark capability unavailable; replan or stop if required
  └─ failed -> Evidence/Health Gate failure path
```

The Node may make a semantic routing decision from the result; it never implements process repair or timeout retry.

## UnityAvailabilityCheck Node

Purpose: expose Unity-specific availability to Planning/Investigation/Implementation/Validation without hiding Unity execution in Graph code.

Runtime probe may observe, as appropriate to the selected profile:

- Unity Editor/BatchMode executable availability
- requested Unity version compatibility
- project path/openability
- Editor connection when an interactive harness is required
- required test/build/profiler harness capability

The probe must not claim Editor/Compile/Player/device health beyond what was actually observed.

Node routing examples:

```text
Validation SubGraph
  -> UnityAvailabilityCheck
      ├─ healthy -> Run EditMode/PlayMode/Build/Profiler Node via Runtime Harness
      ├─ unavailable + gate optional -> continue with explicit unavailable evidence
      └─ unavailable + gate required -> stop/replan, never synthesize PASS
```

## ToolHealthCheck Node

Purpose: query a selected Runtime tool/provider before a graph branch depends on it.

Typical targets:

- Codex CLI/model runner
- Ix/code intelligence provider
- Git/GitHub SCM harness
- Unity test/build/profiler adapters

Runtime ToolHealthProbe owns:

- executable/provider discovery
- bounded health invocation
- timeout/cancellation
- result normalization
- telemetry/evidence capture

Orchestration owns only the consequence:

- continue
- choose approved fallback route
- replan semantically
- request Human Gate if owner-held capability is required
- stop when the required capability cannot be established

## No hidden fallback

A health result may advertise an allowed fallback capability, but the Graph/Policy combination decides whether that fallback is acceptable. Runtime must not silently replace the requested provider/action with another one.

Example:

```text
ToolHealthCheck(Ix)
 -> unavailable
 -> Orchestration may select targeted_source_read
 -> Runtime executes targeted_source_read
```

This preserves the current safe behavior of treating Ix as optional without placing semantic fallback ownership in the Ix subprocess adapter.

## Health vs operational detection

Do not conflate Runtime health probes with Operations failure detection.

| concern | owner |
|---|---|
| immediate executable/Unity/tool availability for current Run | src/unityagent/runtime/health |
| Graph decision after current health result | src/unityagent/orchestration/health_check Node |
| retry storm, latency anomaly, cost drift, repeated tool degradation across runs | src/unityagent/operations/failure_detection |
| quarantine/rollback/force HITL | src/unityagent/operations/runtime_control through src/unityagent/policy/approval |

## Evidence policy

Health evidence is required when the health result controls a required quality gate, mutation permission, production smoke validity, or resume decision. The health result references canonical EvidenceRecords; it does not embed unverifiable self-claims as proof.

## tests

Required contract/integration coverage:

1. Environment healthy/unavailable/failed branches.
2. Unity unavailable does not become Compile/Editor PASS.
3. Tool timeout is handled by src/unityagent/runtime/execution_control, not a Local Loop.
4. Optional provider fallback requires an Orchestration decision.
5. Required provider unavailable blocks/replans according to src/unityagent/policy/graph requirement.
6. Health Node contains no direct subprocess/Unity/tool implementation.
7. Health evidence refs survive src/unityagent/runtime -> src/unityagent/persistence -> eval without re-parsing.
8. Operations anomaly detection cannot directly mutate src/unityagent/runtime/graph without src/unityagent/policy/Approval.

## Acceptance invariant

```text
Graph knows whether it may/should continue.
Runtime knows how to check and execute safely.
Persistence knows what actually happened.
Operations knows whether the system is drifting.
eval knows how to measure the recorded behavior.
```
