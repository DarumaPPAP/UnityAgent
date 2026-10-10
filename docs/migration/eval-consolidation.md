# eval Consolidation

Status: implemented on `refactor/architecture-phase6-eval`

Base: Phase 5 merge `1fa6f9fa3101d099845b66f7a4b5b2917dcb097f`

## Goal

Make `eval/` the single authority for quality measurement, failure attribution, Golden/Actual Behavior grading, regression datasets, reports, and historical replay without moving execution back out of `src/unityagent/runtime/` or durable truth out of `src/unityagent/persistence/`.

```text
Runtime executes
    ↓ structured facts
Persistence preserves durable facts
    ↓ read-only facts / refs
eval measures, attributes, reports, proposes
```

eval never becomes a second Runtime and never edits production src/unityagent/policy, src/unityagent/context, src/unityagent/orchestration, src/unityagent/runtime, src/unityagent/persistence, or Operations definitions.

## Source inventory

Before Phase 6 the evaluation plane was split across:

- `eval/attribution/` and `eval/golden_contracts/` — canonical Phase 1 schemas only;
- `eval/replay/legacy_bundle_normalizer.py` — Phase 1 migration replay;
- `tools/BehaviorEval/` — Actual Behavior normalization, graders and protocol validators;
- `tools/GoldenEval/` — Golden grader, naming grader and regression validators;
- `tests/behavior_eval/` — Behavior suites, protocol schemas and fixtures;
- `tests/golden_tasks/` — Golden cases, schemas and naming fixtures;
- `.ai/eval/` — legacy contracts/taxonomy;
- Unity-Graph-Engineering `BehaviorEvalAdapter` — legacy execution-to-envelope bridge.

This meant the schemas were canonical under `eval/`, but production-quality grading logic and datasets still had competing locations.

## Canonical Phase 6 layout

```text
eval/
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
└─ tests/
```

## Responsibility split

### eval owns

- Golden contract construction;
- Golden/Behavior grading;
- deterministic signal derivation;
- failure attribution;
- Agent-quality denominator eligibility;
- regression summaries;
- historical bundle normalization/replay;
- non-applying `ChangeProposal` generation.

### eval does not own

- process/subprocess execution;
- Codex invocation;
- Unity invocation;
- hard timeout/cancellation/process kill;
- mutation enforcement;
- permission enforcement;
- durable Evidence/Memory/Checkpoint writes;
- Route/Graph/semantic retry decisions;
- production-definition mutation.

## Behavior eval execution split

The pre-Phase-6 `tools/BehaviorEval/run_behavior_eval.py` could launch an external Production adapter with `subprocess`. That behavior cannot be canonical after Phase 3 because actual execution is owned by `src/unityagent/runtime/`.

Phase 6 therefore separates:

```text
legacy compatibility runner
eval/compatibility/behavior_eval/run_behavior_eval.py
    └─ retained read-only for migration/audit only

canonical Behavior evaluator
eval/behavior/run_behavior_eval.py
    └─ grades already-observed candidate/Runtime facts only
```

A new native adapter, `eval/behavior/runtime_adapter.py`, projects canonical `src/unityagent/runtime/contracts/execution_result` facts into Eval. It does not invoke Runtime.

`changed_paths` is copied structurally from `ExecutionResult.changed_paths`; it is never recreated by parsing diff text. An observed empty changed-path set becomes an Agent behavior regression only when the Golden case explicitly expects mutation.

## Dataset consolidation

The Phase-5 datasets are copied byte-equivalent into:

- `eval/datasets/behavior/`
- `eval/datasets/golden/`

Phase 6 tests assert byte parity with the legacy `tests/behavior_eval` and `tests/golden_tasks` trees while those compatibility copies remain.

Legacy dataset path strings are projected in-memory to canonical `eval/datasets/...` paths. The old source trees are not deleted in this phase; deletion remains a Phase 8 Human Gate.

## Golden Contract

`eval/golden_contracts/build_contract.py` projects each legacy GoldenTask into the canonical contract families required by the architecture:

- expected result;
- invariants;
- expected trajectory;
- forbidden behavior;
- evidence requirements.

The builder also exposes a task-only Runtime projection. Expectation-like keys fail closed if they appear in the task payload.

Golden expected content remains evaluator-only and is never injected into Production Runtime prompts or Context materialization.

## Failure attribution and denominator

`eval/attribution/eval-record.schema.yaml` now supports schema `1.1` while remaining backward compatible with Phase-1 `1.0` replay records.

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

Phase 6 keeps only evaluator-side behavior in eval:

- structured changed paths are preserved directly;
- typed Runtime failure is attributed by Eval;
- observed mutation no-op can be classified as Agent behavior regression;
- no process runtime or Graph execution implementation is imported.

Execution remains UnityAgent `src/unityagent/runtime/` authority.

## Historical Production replay

`eval/replay/historical-replay-manifest.yaml` records the external archives already replayed during Phase 1:

- `phase11-naming-04.zip`
- `phase11-mutation-03.zip`
- `production-smoke-20260827-utf8.zip`

Phase 1 records six case directories across these archives. Raw archive contents remain external and are not committed.

`eval/replay/historical_replay.py` accepts supplied bundle directories or ZIP archives and:

- safely rejects archive path traversal;
- runs the existing canonical legacy normalizer;
- preserves structured `metrics.json.changed_paths`;
- does not infer typed failure from prose;
- upgrades compatible eval records to attribution schema 1.1;
- can require coverage of ARCH / NAMING / MUTATION / EVIDENCE namespaces.

The CI regression uses deterministic local protocol bundles to prove all four namespace paths. Real historical archives remain replayable when supplied without duplicating their raw content in Git.

## ChangeProposal boundary

eval can emit `eval/change_proposals/change_proposal` only.

Every ChangeProposal has:

- `status: proposed`;
- `applies_change: false`;
- `requires_human_review: true`.

It cannot directly edit src/unityagent/policy, src/unityagent/context, src/unityagent/orchestration, src/unityagent/runtime, src/unityagent/persistence, src/unityagent/operations, or even eval production definitions.

## Compatibility

`tools/BehaviorEval/*.py` and `tools/GoldenEval/*.py` become thin shims that forward to same-name canonical `eval/behavior` and `eval/golden` modules.

The old subprocess-capable Behavior runner is retained only under `eval/compatibility/behavior_eval/` for migration/audit. It is not the canonical Phase-6 entrypoint.

`.ai/eval` contracts are copied under `eval/compatibility/` for provenance and remain read-only until Phase 8.

## CI

``.github/workflows/validate-agent-contracts.yml` is the canonical PR CI entrypoint. It runs `tools/validate_all.py`, which covers the eval validators and eval / Persistence / Orchestration / Runtime regression suites described above.

The former Eval-specific and Actual Behavior workflows were removed during CI consolidation because they repeated the same canonical validation and created duplicate PR checks. Real Production execution remains a separate manual-only workflow in `.github/workflows/production-smoke.yml`; eval remains post-execution measurement authority.

## Non-goals

Phase 6 does not:

- delete `tests/behavior_eval` or `tests/golden_tasks`;
- delete `.ai/eval`;
- delete compatibility shims;
- archive Unity-Graph-Engineering;
- run the destructive Phase 8 cutover;
- add Operations control;
- re-baseline Production quality thresholds.

Those remain later phases.

## Exit assessment

Phase 6 is complete when:

- grading/data/report authority is canonical under `eval/`;
- Runtime execution is not implemented inside canonical eval control modules;
- native Runtime facts preserve structured changed paths with no diff reparse;
- `not_observed` infrastructure runs are excluded from Agent-quality denominator;
- Golden expectations cannot enter Runtime task projection;
- ARCH/NAMING/MUTATION/EVIDENCE historical replay path is testable;
- eval can propose but cannot apply production changes;
- legacy tools paths are compatibility shims only;
- existing src/unityagent/runtime/orchestration/persistence boundaries remain green.
