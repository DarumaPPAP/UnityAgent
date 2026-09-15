# Orchestration Authority

Status: **canonical**

## Provenance

The current Orchestration layer is the canonical replacement for the semantic portions that historically lived in ContinuationController / ExecutionOrchestrator style code. Historical sources remain provenance only; they are not active authority.

## Ownership

```text
Policy
  ↓ rules / approval / evidence requirements
Orchestration
  ├─ Routing      : choose route/profile/task semantics
  ├─ Graph        : topology only
  ├─ Loop         : semantic continue/replan/exit/TODO selection
  └─ Orchestrator : one semantic transition + Runtime handoff
        ↓
Runtime
  └─ execute selected work + bounded infrastructure retry
        ↓
Persistence
  └─ store workflow/loop state; never decide continuation
```

## Graph topology

`Orchestration/Definitions/development-parent-graph.yaml` declares the Development ParentGraph with first-class Planning, Design Review, Investigation, Implementation, Validation, and Delivery SubGraphs.

Graph owns topology:

- Nodes
- Edges
- Gates
- Parallel-safe declarations
- Local Loop declarations (`from_node_id`, `to_node_id`, outcomes)

Graph does **not** own the semantic continuation implementation.

## Loop Engineering

`Orchestration/Loop/` is the canonical semantic-loop owner.

- `semantic_loop.py` — validate loop declarations and decide `continue / replan / exit / blocked`
- `todo_selector.py` — select the next dependency-ready semantic TODO
- `state_mapping.py` — project a semantic decision into `Persistence/Contracts/LoopControlState` shape without writing it
- `validate.py` — canonical boundary validation

`Orchestration/Contracts/semantic-loop-decision.schema.yaml` is the explicit decision contract.

A Local Loop is an **edge/cycle inside a SubGraph**, not a peer execution plane and not a long-lived controller object.

## Deterministic loop rules

For each Local Loop:

- `continue_on`, `replan_on`, and `exit_on` outcome sets must be disjoint.
- Duplicate outcomes are invalid.
- Unknown outcomes fail closed as `blocked`.
- An explicit semantic blocker returns `blocked`.
- A declared continuation with no semantic progress becomes `replan`.
- `semantic_attempt` is a semantic decision counter only; it is not a hard execution budget.

## Runtime retry boundary

Runtime retry is intentionally different from semantic continuation.

Runtime owns only bounded execution/infrastructure recovery such as:

- timeout retry
- provider re-resolution for the **same capability contract**
- cancellation
- process cleanup
- hard retry ceiling
- hard turn/cost safety limits

Runtime may never change task semantics, route, mutation scope, required evidence, or approval reference as part of fallback. Semantic replan belongs to `Orchestration/Loop` / Routing.

## Forbidden Loop authority

Semantic Loop code must not own:

- `timeout_seconds`
- `hard_retry_ceiling`
- `maximum_retry_attempts`
- `max_turns`
- cost ceilings
- quota / lease accounting
- subprocess/tool execution
- provider selection
- durable Persistence writes
- Runtime mutation enforcement
- Eval grading

There is deliberately no `ContinuationController` class. Loop Engineering is a small set of deterministic functions, not a giant controller.

## TODO selection

Semantic TODO selection is dependency/priority based only. It does not own leases, worker slots, execution quotas, timeouts, or durable scheduling.

Invalid TODO identity or a dependency on an unknown TODO fails closed instead of silently selecting another task.

## Route ownership

Task-fingerprint matching belongs to `Orchestration/Routing/task-routes.yaml`. `Context/Selection/context-catalog.yaml` consumes an explicit route and remains materialization-only.

Unknown fingerprint dimensions are never guessed. Unmatched fingerprints fall back to bounded `generic-planning`; simple read-only tasks may use the fast path.

## Fast path

Simple bounded tasks that do not require semantic replan may use:

```text
Policy -> Orchestration route -> Context -> Runtime -> Verification -> Result
```

The full ParentGraph is used only when semantic coordination adds value.

## State boundary

- `Orchestration/Graph/state_mapping.py` projects `WorkflowState` only.
- `Orchestration/Loop/state_mapping.py` projects `LoopControlState` only.
- Neither module writes Persistence.
- Persistence is the durable source of truth, but it never decides semantic continuation.

## Health boundary

Health-check Nodes depend on Runtime health contracts. Orchestration interprets the result; it contains no OS process, Unity Editor, tool binary, network, or SCM health implementation.

## Non-goals

- no `.ai` deletion in this change
- no Graph repository archive in this change
- no durable state migration
- no Memory/Evidence persistence migration
- no Runtime enforcement moved into Orchestration
- no hard semantic max-turn controller
