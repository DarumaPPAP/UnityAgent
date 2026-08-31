# Orchestration Migration

Status: implementation PR

## Provenance

- UnityAgent base: `b367c2beae94dc0e0315cccf34a1422ca2ae3e41`
- Unity-Graph-Engineering semantic split sources:
  - `Tools/ContinuationController/continuation_controller.py`
  - `Tools/ExecutionOrchestrator/execution_orchestrator.py`
  - `policies/continuation-control.yaml`
  - `policies/execution-orchestration.yaml`
- Graph repository remains a compatibility/reference source until the Phase 8 Human Gate; it is not archived or deleted here.

## Canonical topology

`Orchestration/Definitions/development-parent-graph.yaml` defines one Development ParentGraph with first-class Planning, Investigation, Implementation, Validation, and Delivery SubGraphs. Nodes, Edges, Gates, Parallel planning, and LocalLoops are separate concepts.

LocalLoops are cycles inside a SubGraph. They do not contain hard timeout, hard retry ceiling, max turns, cost ceilings, process cleanup, quota accounting, or leases.

## Split result

From the old ContinuationController, Phase 4 imports only semantic TODO selection and semantic continue/replan/exit decisions. Runtime limits stay in `Runtime/ExecutionControl`; durable lease/quota/state accounting stays out of Orchestration and is deferred to Persistence ownership.

From the old ExecutionOrchestrator, Phase 4 imports only graph transition, route/profile semantic selection, state projections, and Runtime handoff construction. No subprocess, workspace path confinement, mutation enforcement, health implementation, Memory persistence, Evidence persistence, or Eval grading is imported.

## Route ownership

Task-fingerprint route matching formerly embedded in `.ai/context-index.yaml` is migrated to `Orchestration/Routing/task-routes.yaml`. `Context/Selection/context-catalog.yaml` consumes an explicit Orchestration route and remains materialization-only.

Unknown fingerprint dimensions are never guessed. Unmatched fingerprints fall back to bounded `generic-planning`; simple read-only tasks can use the fast path.

## Fast path

Simple bounded tasks that do not require semantic replan may use:

`Policy -> Orchestration route -> Context -> Runtime -> Verification -> Result`

The full ParentGraph is used only when semantic coordination adds value.

## State boundary

`Orchestration/Graph/state_mapping.py` emits projections matching `Persistence/Contracts/WorkflowState` and `LoopControlState`. It does not persist them. Phase 5 remains responsible for authoritative state paths and writeback.

## Health boundary

Health-check Nodes depend on a `RuntimeHealthPort`. They interpret a `HealthCheckResult`; they contain no OS process, Unity Editor, tool binary, network, or SCM health implementation.

## Non-goals

- no `.ai` deletion;
- no Graph repository archive;
- no durable state migration;
- no Memory/Evidence persistence migration;
- no Eval consolidation;
- no Runtime enforcement moved back into Graph code.
