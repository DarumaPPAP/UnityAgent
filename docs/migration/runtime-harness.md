# Runtime / Harness Migration

Status: implementation branch.

## Provenance

- UnityAgent base: `30bbea3d73642715c20d454710bbb0a761f50468`
- Unity-Graph-Engineering import baseline: `b8dc31470f757d87f5d5c45264592ff00ef1e061`

## Ownership cut

Phase 3 transfers actual execution mechanics into `Runtime/`: Codex process execution, cross-platform process-tree cleanup, hard timeout/cancellation/limit enforcement, bounded subprocess/tool dispatch, workspace confinement and mutation scope enforcement, verification observation normalization, ephemeral Runtime evidence capture, Runtime telemetry production, environment/Unity/tool health probing, explicit Test/Performance/SCM command harness surfaces, and Unity Editor artifact dependency scanning/export/impact inspection.

It does **not** transfer semantic ParentGraph/SubGraph/Node selection, TODO selection, semantic replan, semantic retry, durable Checkpoint/Memory/WorkflowState, or Eval grading.

## Split decisions

`.ai/harness/task-contracts/*` are not copied wholesale into Runtime. An already-selected Task Contract may be projected through `Runtime/Harnesses/task_enforcement.py`; Route selection remains outside Runtime.

`.ai/execution-profiles.yaml` is not made Runtime authority. Runtime owns only `Runtime/Profiles/runtime-profiles.yaml`, the hard execution/access facets of a supplied profile. Profile selection remains Orchestration-owned.

Quality Gate definitions remain semantic contracts. Runtime records an observed gate fact but does not aggregate it into an Agent quality grade.

## Codex

`Runtime/Runner/Codex/codex_runner.py` receives an already-materialized prompt and execution request. Golden expectations are rejected. The runner emits canonical `ExecutionResult`, typed `RuntimeFailure`, `MutationEvidence`, structured `changed_paths`, and raw execution artifacts. A mutation no-op is intentionally not converted into a Runtime failure; Eval may classify the observed behavior later.

## Unity Editor artifact graph

The imported scanner is an Asset dependency graph harness. It must never be treated as the agent ParentGraph. Its JSON output may feed later Context/Investigation consumers.

## Compatibility

The legacy `.ai` tree remains read-only until Phase 8. Unity-Graph-Engineering remains active for semantic Graph/Loop ownership until Phase 4 and for later cutover validation. No archive/delete action is part of Phase 3.

## Exit checks

- one Runtime surface owns subprocess execution and process cleanup;
- hard timeout/cancellation are Runtime concerns;
- scope escape is fail-closed;
- unavailable health never becomes PASS;
- structured changed paths survive execution without diff reparsing;
- Runtime source contains no Eval grading or semantic Graph controller imports;
- existing Phase 1/2 contract validation remains green.
