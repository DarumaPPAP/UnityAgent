# Phase 2 — Policy + Context

Status: implemented on `refactor/architecture-phase2-policy-context`

Base: Phase 1 merge `e141bcf5c13d98f8caa7a203046670a73d28dbf9`

## Policy migration

- `.ai/user-policy.yaml` is copied byte-for-byte to `Policy/User/user-policy.yaml`.
- `.ai/harness/risk-levels.yaml` is copied byte-for-byte to `Policy/Risk/risk-levels.yaml`.
- MCP activation is split by authority without dropping repository/ownership facts; those are preserved in `Policy/Contracts/repository-ownership.yaml`.
- MCP activation is split by authority:
  - context description/catalog loading -> `Context/Selection/mcp-selection.yaml`
  - permission/trust/approval requirements -> `Policy/`
  - actual tool exposure -> `Runtime/Permissions/mcp-activation.yaml`
- Existing legacy sources are retained for compatibility and are not deleted in Phase 2.

## Context migration

- Context Packs are copied losslessly to `Context/Packs/`.
- compressed Knowledge is copied losslessly to `Context/Retrieval/Knowledge/`.
- Context Budget is canonical at `Context/Budget/context-budget.yaml`. The mature budget engine is migrated byte-exact as an audited compatibility engine and exposed through `Context/Budget/context_budget_runtime.py`, which overrides the contract path to the canonical Context location.
- Prompt templates are copied losslessly to `Context/Prompt/Templates/`.
- Prompt catalog records the no-Golden-leak review.
- `Context/Selection/context-catalog.yaml` is a materialization catalog only; it does not claim route-decision authority.
- `MaterializedContextView`, `ContextFingerprint`, and `MemoryProjection` contracts are first-class Context contracts.
- `Context/Assembly/materialize_context.py` requires an explicit Route ID, resolves required Context entries, records unresolved bindings/external observations instead of guessing, and produces a bounded current-call view. It does not persist WorkflowState, Checkpoint, Memory truth, or Evidence truth.

## Compatibility boundary

`Context/Compatibility/legacy-path-map.yaml` is the only new read-only compatibility authority. It maps migrated legacy refs to canonical paths and names remaining Phase 3/4 dependencies through `compatibility://` keys.

No compatibility write API exists. `resolve_for_write` fails closed.

Lossless migrated Context Packs and Knowledge may still contain historical legacy source-ref strings; those are resolved through the compatibility resolver at materialization time and are not treated as canonical ownership.

## Context Manifest split

The previous monolithic Context Manifest runtime mixed context materialization with execution evidence, graph projection, retry status, and harness facts.

Phase 2 creates a context-only manifest:
- current-call materialized context
- context budget
- unresolved bindings
- attempt provenance

Execution Evidence remains Runtime/Persistence work for later phases. Graph state/topology remains Orchestration work for Phase 4.

## Guards

- `Policy/Validators/validate_user_policy_equivalence.py` rejects any user-policy or risk-policy loss.
- `Context/Validators/validate_stale_paths.py` rejects direct legacy path references on canonical operational surfaces.
- New legacy-path writes are forbidden.
- Old legacy files remain present and read-only until the explicit destructive cutover gate.

## Phase 2 exit

- New Policy paths are canonical: yes.
- Existing user-specific policy semantics are lossless: yes, byte-exact check.
- Context is modeled as a materialized current-call view: yes.
- Prompt templates are under Context and reviewed for Golden expectation leakage: yes.
- Context Packs / Knowledge / Budget have canonical Context locations: yes.
- Old legacy tree is still available only for bounded compatibility reads: yes.
- No new legacy writes are allowed: yes.
- Deletion of the legacy tree remains deferred to Phase 8: yes.
