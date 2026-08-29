# Phase 6 — Eval Consolidation

Status: implemented on `refactor/architecture-phase6-eval`

Base: Phase 5 merge `1fa6f9fa3101d099845b66f7a4b5b2917dcb097f`

## Goal

Make `Eval/` the single authority for quality measurement, failure attribution, Golden/Actual Behavior grading, regression datasets, reports, and historical replay without moving execution back out of `Runtime/` or durable truth out of `Persistence/`.

```text
Runtime executes
    ↓ structured facts
Persistence preserves durable facts
    ↓ read-only facts / refs
Eval measures, attributes, reports, proposes
```

Eval never becomes a second Runtime and never edits production Policy, Context, Orchestration, Runtime, Persistence, or Operations definitions.

## Source inventory

Before Phase 6 the evaluation plane was split across:

- `Eval/Attribution/` and `Eval/GoldenContracts/` — canonical Phase 1 schemas only;
- `Eval/Replay/legacy_bundle_normalizer.py` — Phase 1 migration replay;
- `Tools/BehaviorEval/` — Actual Behavior normalization, graders and protocol validators;
- `Tools/GoldenEval/` — Golden grader, naming grader and regression validators;
- `Tests/BehaviorEval/` — Behavior suites, protocol schemas and fixtures;
- `Tests/GoldenTasks/` — Golden cases, schemas and naming fixtures;
- `.ai/eval/` — legacy contracts/taxonomy;
- Unity-Graph-Engineering `BehaviorEvalAdapter` — legacy execution-to-envelope bridge.

This meant the schemas were canonical under `Eval/`, but production-quality grading logic and datasets still had competing locations.

## Canonical Phase 6 layout

```text
Eval/
├─ Attribution/
│  ├─ eval-record.schema.yaml
│  ├─ failure-taxonomy.yaml
│  └─ attribution.py
├─ Behavior/
│  ├─ derive_signals.py
│  ├─ normalize_result.py
│  ├─ runtime_adapter.py
│  ├─ run_behavior_eval.py
│  └─ validators...
├─ Golden/
│  ├─ naming_grader.py
│  ├─ project_regression_graph.py
│  ├─ run_golden_evals.py
│  └─ validators...
├─ GoldenContracts/
│  ├─ golden-contract.schema.yaml
│  └─ build_contract.py
├─ Datasets/
│  ├─ Behavior/
│  └─ Golden/
├─ Replay/
│  ├─ legacy_bundle_normalizer.py
│  ├─ historical_replay.py
│  └─ historical-replay-manifest.yaml
├─ ChangeProposals/
│  ├─ change-proposal.schema.yaml
│  └─ change_proposal.py
├─ Compatibility/
│  └─ legacy contracts / old execution runner
└─ Tests/
```

## Responsibility split

### Eval owns

- Golden contract construction;
- Golden/Behavior grading;
- deterministic signal derivation;
- failure attribution;
- Agent-quality denominator eligibility;
- regression summaries;
- historical bundle normalization/replay;
- non-applying `ChangeProposal` generation.

### Eval does not own

- process/subprocess execution;
- Codex invocation;
- Unity invocation;
- hard timeout/cancellation/process kill;
- mutation enforcement;
- permission enforcement;
- durable Evidence/Memory/Checkpoint writes;
- Route/Graph/semantic retry decisions;
- production-definition mutation.

## Behavior Eval execution split

The pre-Phase-6 `Tools/BehaviorEval/run_behavior_eval.py` could launch an external Production adapter with `subprocess`. That behavior cannot be canonical after Phase 3 because actual execution is owned by `Runtime/`.

Phase 6 therefore separates:

```text
legacy compatibility runner
Eval/Compatibility/BehaviorEval/run_behavior_eval.py
    └─ retained read-only for migration/audit only

canonical Behavior evaluator
Eval/Behavior/run_behavior_eval.py
    └─ grades already-observed candidate/Runtime facts only
```

A new native adapter, `Eval/Behavior/runtime_adapter.py`, projects canonical `Runtime/Contracts/ExecutionResult` facts into Eval. It does not invoke Runtime.

`changed_paths` is copied structurally from `ExecutionResult.changed_paths`; it is never recreated by parsing diff text. An observed empty changed-path set becomes an Agent behavior regression only when the Golden case explicitly expects mutation.

## Dataset consolidation

The Phase-5 datasets are copied byte-equivalent into:

- `Eval/Datasets/Behavior/`
- `Eval/Datasets/Golden/`

Phase 6 tests assert byte parity with the legacy `Tests/BehaviorEval` and `Tests/GoldenTasks` trees while those compatibility copies remain.

Legacy dataset path strings are projected in-memory to canonical `Eval/Datasets/...` paths. The old source trees are not deleted in this phase; deletion remains a Phase 8 Human Gate.

## Golden Contract

`Eval/GoldenContracts/build_contract.py` projects each legacy GoldenTask into the canonical contract families required by the architecture:

- expected result;
- invariants;
- expected trajectory;
- forbidden behavior;
- evidence requirements.

The builder also exposes a task-only Runtime projection. Expectation-like keys fail closed if they appear in the task payload.

Golden expected content remains evaluator-only and is never injected into Production Runtime prompts or Context materialization.

## Failure attribution and denominator

`Eval/Attribution/eval-record.schema.yaml` now supports schema `1.1` while remaining backward compatible with Phase-1 `1.0` replay records.

Phase-6 attribution uses typed facts only:

| Failure class | Attribution | Observation | Agent quality denominator |
|---|---|---|---|
| none / observed success | none | observed | yes |
| `agent_behavior_regression` | agent_quality | observed | yes |
| `runtime_timeout` | runtime_infrastructure | not_observed | no |
| `runtime_protocol_failure` | runtime_infrastructure | not_observed | no |
| `runtime_cancelled` | runtime_infrastructure | not_observed | no |
| `runtime_tool_unavailable` | runtime_infrastructure | not_observed | no |
| `runtime_permission_denied` | policy_or_permission | not_observed | no |
| `evaluator_contract_failure` | evaluator_infrastructure | not_observed | no |
| `task_fixture_invalid` | fixture_invalid | not_observed | no |
| `unavailable_required_evidence` | unavailable_evidence | not_observed | no |

No failure class is inferred from response text, stderr wording, or missing fields.

The Behavior summary computes `regression_pass_rate` over `quality_denominator_eligible` runs rather than all attempted runs. Infrastructure defects therefore cannot silently lower Agent quality.

## BehaviorEvalAdapter cutover

The legacy Graph `BehaviorEvalAdapter` mixed two concerns:

1. launch/bridge Production execution;
2. normalize/attribute evaluation facts.

Phase 6 keeps only evaluator-side behavior in Eval:

- structured changed paths are preserved directly;
- typed Runtime failure is attributed by Eval;
- observed mutation no-op can be classified as Agent behavior regression;
- no process runtime or Graph execution implementation is imported.

Execution remains UnityAgent `Runtime/` authority.

## Historical Production replay

`Eval/Replay/historical-replay-manifest.yaml` records the external archives already replayed during Phase 1:

- `phase11-naming-04.zip`
- `phase11-mutation-03.zip`
- `production-smoke-20260827-utf8.zip`

Phase 1 records six case directories across these archives. Raw archive contents remain external and are not committed.

`Eval/Replay/historical_replay.py` accepts supplied bundle directories or ZIP archives and:

- safely rejects archive path traversal;
- runs the existing canonical legacy normalizer;
- preserves structured `metrics.json.changed_paths`;
- does not infer typed failure from prose;
- upgrades compatible Eval records to attribution schema 1.1;
- can require coverage of ARCH / NAMING / MUTATION / EVIDENCE namespaces.

The CI regression uses deterministic local protocol bundles to prove all four namespace paths. Real historical archives remain replayable when supplied without duplicating their raw content in Git.

## ChangeProposal boundary

Eval can emit `Eval/ChangeProposals/ChangeProposal` only.

Every ChangeProposal has:

- `status: proposed`;
- `applies_change: false`;
- `requires_human_review: true`.

It cannot directly edit Policy, Context, Orchestration, Runtime, Persistence, Operations, or even Eval production definitions.

## Compatibility

`Tools/BehaviorEval/*.py` and `Tools/GoldenEval/*.py` become thin shims that forward to same-name canonical `Eval/Behavior` and `Eval/Golden` modules.

The old subprocess-capable Behavior runner is retained only under `Eval/Compatibility/BehaviorEval/` for migration/audit. It is not the canonical Phase-6 entrypoint.

`.ai/eval` contracts are copied under `Eval/Compatibility/` for provenance and remain read-only until Phase 8.

## CI

`.github/workflows/validate-eval.yml` validates:

- Phase-1 canonical Eval/replay contracts;
- Phase-6 attribution and denominator behavior;
- Runtime -> Eval structured fact preservation;
- observed mutation no-op classification;
- GoldenContract construction and no-leak task projection;
- dataset byte parity;
- ChangeProposal non-applying invariant;
- four-namespace historical replay path;
- canonical Golden/Behavior validators;
- Persistence / Orchestration / Runtime regression suites.

`.github/workflows/actual-behavior-eval.yml` no longer claims Unity-Graph-Engineering owns Production execution. It documents UnityAgent `Runtime/` as the actual execution authority and Eval as post-execution measurement authority.

## Non-goals

Phase 6 does not:

- delete `Tests/BehaviorEval` or `Tests/GoldenTasks`;
- delete `.ai/eval`;
- delete compatibility shims;
- archive Unity-Graph-Engineering;
- run the destructive Phase 8 cutover;
- add Operations control;
- re-baseline Production quality thresholds.

Those remain later phases.

## Exit assessment

Phase 6 is complete when:

- grading/data/report authority is canonical under `Eval/`;
- Runtime execution is not implemented inside canonical Eval control modules;
- native Runtime facts preserve structured changed paths with no diff reparse;
- `not_observed` infrastructure runs are excluded from Agent-quality denominator;
- Golden expectations cannot enter Runtime task projection;
- ARCH/NAMING/MUTATION/EVIDENCE historical replay path is testable;
- Eval can propose but cannot apply production changes;
- legacy Tools paths are compatibility shims only;
- existing Runtime/Orchestration/Persistence boundaries remain green.
