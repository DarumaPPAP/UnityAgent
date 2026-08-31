# Persistence Migration

Status: implemented on `refactor/architecture-phase5-persistence`.

## Provenance

- UnityAgent base: `1b885fb58bc8a662166b176c1db2c30fb20931c1`
- Unity-Graph-Engineering compatibility reference: `b8dc31470f757d87f5d5c45264592ff00ef1e061`
- Split references:
  - `Tools/LayeredMemoryController/layered_memory_controller.py`
  - `policies/memory-layering.yaml`
  - `schemas/run-state.schema.json`
  - `schemas/continuation-state.schema.yaml`

The Graph repository remains a compatibility/audit reference until the Phase 8 Human Gate. No destructive cutover is performed here.

## Canonical ownership

Persistence is the only durable-truth owner for:

- `ExecutionState`
- `WorkflowState`
- `LoopControlState`
- `RunCheckpoint`
- `SessionRecord`
- `MemoryRecord`
- `EvidenceRecord`

Orchestration returns state projections/patches; Runtime emits execution facts and captured Evidence; Context reads bounded Memory projections. None of those modules becomes a durable store.

## Physical separation

A caller-selected Persistence root is organized as:

```text
<root>/
├─ runs/<run_id>/
│  ├─ current/
│  │  ├─ execution-state.json
│  │  ├─ workflow-state.json
│  │  └─ loops/<loop_id>.json
│  ├─ snapshots/
│  │  ├─ execution-state/
│  │  ├─ workflow-state/
│  │  └─ loop-control-state/
│  └─ checkpoints/<checkpoint_id>.json
├─ sessions/<session_id>.json
├─ memory/
│  ├─ records/<memory_id>.json
│  ├─ safe-index.jsonl
│  └─ events.jsonl
├─ evidence/
│  ├─ records/<evidence_id>.json
│  └─ events.jsonl
└─ migration/
   └─ checkpoint-events.jsonl
```

`runs/<run_id>/current/execution-state.json` is the single authoritative current ExecutionState path.

## Checkpoint semantics

A checkpoint is an immutable bundle of references to content-addressed state snapshots. It does not contain Memory and it does not become Evidence.

`RunCheckpoint` schema `1.1` adds:

- snapshot hashes for ExecutionState / WorkflowState / LoopControlState;
- a full `DefinitionFingerprint`;
- a checkpoint integrity hash;
- `migration_from` provenance.

Restore replaces only current State records. It does not rewind Memory or Evidence.

Historical checkpoint schema `1.0` is read through compatibility logic. Migration creates a new `1.1` checkpoint and preserves the original. A legacy checkpoint that points at mutable `current/` state is rejected as unsafe to migrate.

## Resume compatibility

`Persistence/Resume/resume.py` implements the Phase 0 resume matrix:

- identical fingerprint -> resume;
- Policy change -> fail closed unless explicitly declared compatible, then re-evaluate Policy/Approval;
- Prompt/Context change before an action is issued -> re-materialize Context;
- Prompt/Context change after action issue -> do not reuse the action; return to a safe semantic boundary;
- active Graph revision mismatch -> require an exact node mapping;
- Runtime/tool schema change before execution -> revalidate Runtime;
- possible in-flight external action + Runtime/tool change -> block and reconcile side effects;
- checkpoint schema change -> require a tested migration;
- Evidence schema change -> keep historical Evidence immutable and use a versioned reader;
- architecture boundary change -> Human review.

## Evidence

Runtime capture is not durable truth until appended to `Persistence/Evidence`.

Evidence is append/immutable-oriented:

- same `evidence_id` + same record is idempotent;
- same `evidence_id` + different record is rejected;
- Runtime `ExecutionEvidence.status` is mapped losslessly to durable `verification_status`;
- `gate_outcome`, payload/hash, provenance, and full DefinitionFingerprint are retained;
- historical Evidence is never rewritten merely to resume a run.

## Memory

The old layered controller is split by authority:

```text
Runtime EvidenceCapture
        │
        ▼
Persistence Evidence
        │
        ▼
Persistence Memory
        │
        └─ durable record / promotion gate
        │
        ▼
Context Retrieval/Memory
        └─ read-only bounded projection
```

Raw L0 Evidence is not reclassified as Memory. Legacy L1/L2/L3 records are normalized into durable Memory records that retain Evidence ancestry.

Memory invariants:

- immutable record identity; use a new record plus `supersedes`/`conflicts_with`;
- at least one source Evidence reference;
- derived Memory cannot reduce source Memory scope;
- non-personal profiles read only the safe index;
- promotion requires explicit review approval;
- knowledge/policy candidates require verified confidence;
- user-policy candidate promotion additionally requires a Human Gate;
- Persistence never writes Policy or authored Knowledge directly.

## Compatibility

Legacy Graph run-state normalization requires an explicit node -> SubGraph mapping and does not guess semantic LoopControlState from legacy attempt counters. Native continuation-controller output is explicitly rejected as durable state because it is a decision projection, not stored truth.

Legacy layered Memory normalization preserves source lineage and separates raw Evidence candidates from Memory records. Raw Evidence candidates require run/step/fingerprint enrichment before append to the canonical Evidence store.

## Validation

Phase 5 tests cover:

- one authoritative ExecutionState path;
- immutable checkpoint state snapshots;
- checkpoint integrity/tamper detection;
- checkpoint restore without Memory/Evidence rollback;
- schema `1.0 -> 1.1` checkpoint migration by copy;
- exact and fail-closed resume decisions;
- in-flight tool revision mismatch;
- Evidence append immutability and Runtime adapter fidelity;
- Memory immutability, safe-scope retrieval, scope-downgrade rejection and promotion gates;
- read-only Context Memory projection;
- Session/Checkpoint separation;
- legacy Graph state normalization;
- legacy layered Memory split;
- no Runtime/Orchestration implementation import into Persistence.

## Non-goals

Phase 5 does not delete compatibility sources, remove legacy source trees, archive Unity-Graph-Engineering, consolidate Eval, or implement Operations control. Those remain later-phase responsibilities.
