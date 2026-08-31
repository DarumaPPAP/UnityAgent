# Production Re-baseline

Status: specification + integration implementation  
Base: canonical cutover merge `5345dfb1238abd7ed84f1eb9eea60f79e4a1e2e0`  
Canonical repository: `DarumaPPAP/UnityAgent`

## Goal

This migration does not redesign the architecture. It measures the post-cutover UnityAgent through real Codex-backed production execution and freezes a new quality baseline only from observed, attributable evidence.

It turns the canonical single-repository architecture into a measurable production baseline:

```text
Production Smoke cases
  ├─ ARCH
  ├─ NAMING
  ├─ MUTATION
  └─ EVIDENCE
        ↓
Orchestration → Context → Runtime → Persistence
        ↓
Eval normalization / grading
        ↓
Unified Failure Taxonomy
        ↓
RebaselineSummary
        ↓
Historical replay coverage
        ↓
Baseline eligibility / freeze
```

## Core decision

The four Production Smoke cases keep independent immutable evidence, but taxonomy and baseline judgment are performed once over the complete suite.

Do not run four separate taxonomy pipelines.

```text
4 case executions
      ↓
one candidate-results document
      ↓
one Behavior Eval
      ↓
one taxonomy aggregation
      ↓
one RebaselineSummary
```

This keeps case-level diagnosis while preventing four competing baseline summaries.

## Production cases

The canonical Production Smoke suite remains:

- `GOLDEN-ARCH-001`
- `GOLDEN-NAMING-001`
- `GOLDEN-MUTATION-001`
- `GOLDEN-EVIDENCE-001`

The suite must use real Runtime execution. Fake Runtime, fake Codex, replay-only evidence, or Golden-derived answers cannot satisfy production observation.

### ARCH

Measures architecture judgment without implementation leakage or unnecessary abstraction.

### NAMING

Measures naming policy and type-responsibility judgment from actual Agent output.

### MUTATION

Measures bounded source mutation, structured `changed_paths`, compile evidence and mutation-scope enforcement.

### EVIDENCE

Measures evidence honesty. Compile evidence must not be expanded into claims about Unity Editor, Runtime, Player, target device, visual quality or performance unless those facts were actually observed.

## Execution ownership

Authority does not change during rebaseline.

```text
Orchestration selects semantic route/profile
Context materializes current-call input
Runtime executes and hard-enforces
Persistence stores durable evidence
Eval grades, attributes and reports
```

Eval must never invoke Codex or become a second Runtime.

## Golden isolation

Production Runtime input must not contain:

- Golden expected result
- required/forbidden signals
- expected route
- hidden grader information
- evaluator-only acceptance answers

Production prompts remain user-realistic. Golden content enters only after execution, inside Eval.

## Unified taxonomy

`Eval/Attribution/failure-taxonomy.yaml` remains the taxonomy authority.

The rebaseline distinguishes two layers:

### Canonical attribution taxonomy

- `agent_behavior_regression`
- `runtime_timeout`
- `runtime_protocol_failure`
- `runtime_cancelled`
- `runtime_tool_unavailable`
- `runtime_permission_denied`
- `evaluator_contract_failure`
- `task_fixture_invalid`
- `unavailable_required_evidence`

These are used for attribution and denominator eligibility.

### Diagnostic failure details

Examples:

- `routing_miss`
- `context_miss`
- `policy_violation`
- `harness_violation`
- `mutation_violation`
- `evidence_overclaim`
- `model_failure`
- `broken_eval`
- `unavailable_evidence`

Diagnostic details explain the failure but do not become competing top-level baseline taxonomies.

For an observed, denominator-eligible failed case, the rebaseline records `agent_behavior_regression` once and keeps the detailed causes separately.

For a `not_observed` case, the rebaseline requires a typed infrastructure / permission / fixture / unavailable-evidence class. It must not infer failure attribution from response prose or stderr wording.

## Quality denominator

Only observed Agent behavior belongs in the Agent quality denominator.

```text
observed + eligible
        ↓
Agent quality denominator

not_observed / infrastructure / evaluator / fixture / permission / unavailable
        ↓
excluded from denominator
```

Infrastructure defects must never silently reduce Agent quality metrics.

## RebaselineSummary

The migration introduces one canonical aggregate artifact:

`Eval/Rebaseline/rebaseline-summary.schema.yaml`

Generated run artifact:

`Artifacts/ProductionSmoke/<run-id>/rebaseline-summary.json`

The summary records:

- source repository and revision;
- model / reasoning effort / Codex version;
- production observation state;
- all available case results;
- canonical taxonomy counts;
- diagnostic failure-detail counts;
- quality denominator and regression pass rate;
- per-case DefinitionFingerprint;
- historical replay coverage;
- baseline eligibility and reasons.

## Historical replay

Historical replay remains a separate evidence source and is never substituted for current production execution.

The final baseline requires replay coverage for:

- ARCH
- NAMING
- MUTATION
- EVIDENCE

`Eval/Replay/historical_replay.py` remains the replay authority.

A Production Smoke run may first produce:

`smoke_passed_pending_historical`

and later be rebuilt with historical replay evidence into:

`baseline_ready`

This avoids duplicating taxonomy while keeping historical provenance explicit.

## Baseline eligibility

A baseline is eligible only when all of the following are true:

1. Exactly the four canonical Production Smoke cases are present.
2. All four cases are `observed`.
3. All four cases are quality-denominator eligible.
4. All four cases pass.
5. `regression_pass_rate == 1.0`.
6. Canonical infrastructure/evaluator/fixture/permission/unavailable taxonomy counts are zero.
7. Every case has a valid canonical DefinitionFingerprint.
8. Historical replay status is `passed` with ARCH/NAMING/MUTATION/EVIDENCE coverage.
9. Golden expectation leakage remains zero.
10. Mutation and evidence boundaries remain enforced.

A run that is not observed is not a failed baseline; it is not a baseline candidate.

## Status model

`RebaselineSummary.status` uses:

- `smoke_passed_pending_historical` — current Production Smoke is clean, historical replay is not yet attached;
- `baseline_ready` — all production and historical requirements are satisfied;
- `not_eligible` — observed regression or another baseline requirement failed;
- `blocked_not_run` — reserved for explicit pre-execution blocking evidence.

`baseline_ready` is not the same as committing a baseline definition. Baseline freeze remains a reviewed repository change.

## Baseline freeze

After a `baseline_ready` summary is produced:

1. review the summary and retained run evidence;
2. verify the source revision and Runtime/model identity;
3. freeze the accepted baseline through a dedicated PR;
4. never rewrite old baseline evidence in place;
5. future definition/model changes compare against the frozen baseline by recorded fingerprints and typed metrics.

Do not retry until a convenient result appears and then call that the baseline. The canonical Production Smoke suite uses one Agent attempt per case.

## Stop conditions

Stop and review before baseline freeze if:

- an unexplained Agent regression appears;
- any Golden expectation reaches Runtime/Context;
- changed paths are reconstructed from lossy prose rather than canonical Runtime facts;
- a `not_observed` run lacks a typed non-Agent attribution;
- historical replay loses canonical facts;
- mutation exceeds allowed scope;
- evidence claims exceed observed evidence;
- source revision, model identity or DefinitionFingerprint is missing;
- Eval attempts to apply production changes directly.

## Definition of Done

The production rebaseline is complete only when:

- real Codex-backed Production Smoke has executed all four cases;
- one unified taxonomy/evaluation summary exists;
- ARCH/NAMING/MUTATION/EVIDENCE are all observed and passed;
- quality denominator is 4/4 and regression pass rate is 1.0;
- historical replay covers all four namespaces;
- DefinitionFingerprints and Runtime identity are recorded;
- `RebaselineSummary` is `baseline_ready`;
- the accepted baseline is frozen through review without rewriting historical evidence.
