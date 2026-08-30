# Phase 10 — Baseline Comparator / Regression Gate

Status: implementation candidate  
Base: Phase 9 frozen baseline merge `a011628dee31353af32866ce3e845ead0363e6b6`  
Canonical repository: `DarumaPPAP/UnityAgent`

## Goal

Phase 10 turns the reviewed Phase 9 baseline from a stored quality fact into an operational regression boundary.

It answers four different questions without conflating them:

1. Is the candidate comparable to the frozen baseline?
2. Was current Production behavior actually observed?
3. Did observed Agent behavior regress?
4. Did the evaluation/runtime definition change enough that a new baseline is required?

```text
Frozen Phase 9 baseline
        │
        │ comparison authority
        ▼
Candidate Production Smoke
        │
        ▼
Actual Behavior Eval
        │
        ▼
Candidate RebaselineSummary
        │
        ▼
┌──────────────────────────────┐
│ Phase 10 Baseline Comparator │
└──────────────┬───────────────┘
               │
      ┌────────┼─────────┬──────────────────┐
      ▼        ▼         ▼                  ▼
     PASS   REGRESSION  INCONCLUSIVE   DEFINITION DRIFT
      │        │         │                  │
      ▼        ▼         ▼                  ▼
   continue   block     block        REBASELINE_REQUIRED
```

## Baseline authority

Phase 10 does not create a second baseline.

The baseline authority remains:

`Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml`

The comparator validates that freeze through the existing Phase 9 `BaselineFreeze` contract before comparing anything.

The frozen baseline is never automatically updated after a passing candidate. A future baseline replacement still requires:

```text
Production observation
  → RebaselineSummary
  → historical replay when freezing a new baseline
  → baseline_ready
  → dedicated reviewed Freeze PR
```

## Candidate input

The Phase 10 candidate input is the existing Phase 9 `RebaselineSummary` generated from a new Production Smoke run:

`Artifacts/ProductionSmoke/<candidate-run-id>/rebaseline-summary.json`

Phase 10 does not introduce a second grading pipeline. It reuses the canonical facts already produced by:

```text
Orchestration
  → Context
  → Runtime
  → Persistence
  → Behavior Eval
  → RebaselineSummary
```

## Historical Replay boundary

Historical Replay is **not required for every Phase 10 candidate**.

Phase 10 is a current Production regression gate. A clean candidate may still have:

`RebaselineSummary.status = smoke_passed_pending_historical`

and pass Phase 10 if current Production behavior is fully observed and comparable.

Historical Replay becomes mandatory again only when a candidate is proposed as a new frozen baseline.

This preserves the Phase 9 distinction:

```text
Current Production quality      → Production Smoke / Eval
Historical compatibility        → Historical Replay
Reviewed baseline acceptance    → Baseline Freeze
```

## Comparability first

A candidate must not be called a regression until the comparator establishes that the baseline and candidate use a compatible evaluation/runtime definition.

### `strict_comparable`

No tracked comparison drift is present.

This normally occurs only when the same source/runtime identity is repeated.

### `comparable_with_drift`

The evaluation contract is stable while expected implementation/tooling facts changed.

Informational drift includes:

- source revision;
- Codex CLI version;
- per-case `context_revision`.

These facts are recorded in the report but do not by themselves block quality comparison.

### `not_comparable`

A definition/runtime identity changed enough that Phase 10 must not label the result as a regression against the Phase 9 baseline.

Blocking runtime drift:

- model;
- reasoning effort.

Blocking DefinitionFingerprint drift:

- `architecture_version`;
- `policy_revision`;
- `prompt_revision`;
- `graph_revision`;
- `runtime_profile_revision`;
- `tool_schema_revision`;
- `checkpoint_schema_revision`;
- `evidence_schema_revision`;
- `eval_contract_revision`.

Result:

`REBASELINE_REQUIRED`

This is deliberately conservative. If a future phase wants to experiment across policy/model changes, it should add an explicit experiment comparison mode instead of weakening the production regression contract.

### `insufficient_evidence`

The candidate does not contain enough canonical comparison evidence, for example a missing per-case DefinitionFingerprint.

Result:

`BLOCK_INCONCLUSIVE`

Missing comparison evidence is not treated as Agent regression and is not silently accepted.

## Gate decisions

Phase 10 exposes exactly four gate decisions.

| Decision | Meaning | Merge guidance |
| --- | --- | --- |
| `PASS` | Comparable candidate meets the frozen Production baseline | May proceed |
| `BLOCK_REGRESSION` | Fully observed Agent behavior is worse than the frozen baseline | Block / investigate |
| `BLOCK_INCONCLUSIVE` | Production quality could not be fully established | Block / rerun or repair infrastructure |
| `REBASELINE_REQUIRED` | Evaluation/runtime definition changed | Review definition change; do not call it regression |

## Decision order

The comparator is fail-closed and evaluates in this order:

```text
Validate frozen baseline
        │
        ▼
Validate candidate RebaselineSummary
        │
        ▼
Comparability evidence present?
   │ no                 │ yes
   ▼                    ▼
BLOCK_INCONCLUSIVE   Definition comparable?
                        │ no             │ yes
                        ▼                ▼
              REBASELINE_REQUIRED   Fully observed / eligible?
                                         │ no           │ yes
                                         ▼              ▼
                                BLOCK_INCONCLUSIVE   Agent regression?
                                                        │ yes      │ no
                                                        ▼          ▼
                                               BLOCK_REGRESSION   PASS
```

## Regression definition

An Agent regression requires observed Agent behavior.

Canonical regression signal:

```text
observation_state = observed
quality_denominator_eligible = true
status = failed
```

or an active canonical:

`agent_behavior_regression`

A lower fully-observed quality result than the frozen 4/4 baseline is also a regression.

## Non-Agent failure boundary

The following do not become Agent regressions:

- `runtime_timeout`;
- `runtime_protocol_failure`;
- `runtime_cancelled`;
- `runtime_tool_unavailable`;
- `runtime_permission_denied`;
- `evaluator_contract_failure`;
- `task_fixture_invalid`;
- `unavailable_required_evidence`.

They produce `BLOCK_INCONCLUSIVE` because the candidate has not proven that the frozen Production quality is maintained.

This preserves Phase 9 attribution semantics instead of turning infrastructure problems into fake Agent regressions.

## Output artifact

Phase 10 writes:

`Artifacts/ProductionSmoke/<candidate-run-id>/baseline-comparison.json`

The report records:

- frozen baseline identity;
- candidate identity;
- comparability status;
- blocking and informational drift;
- missing comparison evidence;
- baseline and candidate quality facts;
- per-case transition from frozen `passed` state;
- candidate canonical failure taxonomy;
- final gate decision and machine-readable reasons.

Example shape:

```json
{
  "schema_version": "1.0",
  "phase": 10,
  "comparability": {
    "status": "comparable_with_drift"
  },
  "quality_delta": {
    "quality_passed_delta": 0,
    "regression_pass_rate_delta": 0.0
  },
  "gate": {
    "decision": "PASS",
    "reasons": ["candidate_meets_frozen_baseline"]
  }
}
```

## CLI

Generate a comparison report without making the command fail on a non-PASS decision:

```powershell
python .\Eval\Regression\compare_baseline.py --baseline ".\Eval\Rebaseline\Baselines\phase9-baseline-20260830-09.yaml" --candidate ".\Artifacts\ProductionSmoke\<run-id>\rebaseline-summary.json"
```

Use as a regression gate:

```powershell
python .\Eval\Regression\compare_baseline.py --baseline ".\Eval\Rebaseline\Baselines\phase9-baseline-20260830-09.yaml" --candidate ".\Artifacts\ProductionSmoke\<run-id>\rebaseline-summary.json" --require-pass
```

Gate-specific exit codes:

- `0` — PASS;
- `10` — BLOCK_REGRESSION;
- `11` — BLOCK_INCONCLUSIVE;
- `12` — REBASELINE_REQUIRED;
- `20` — invalid input/contract/comparison failure.

Validate an already-written report without rerunning Production behavior:

```powershell
python .\Eval\Regression\validate_baseline_comparison.py ".\Artifacts\ProductionSmoke\<run-id>\baseline-comparison.json" --require-pass
```

All repository text reads/writes in the Phase 10 path explicitly use UTF-8.

For PowerShell inspection, continue to use:

```powershell
Get-Content ".\Artifacts\ProductionSmoke\<run-id>\baseline-comparison.json" -Raw -Encoding UTF8
```

## GitHub Actions operating model

`.github/workflows/baseline-regression-gate.yml` is intentionally `workflow_dispatch` only.

Real Codex-backed Production Smoke is not executed automatically for every PR because it has API cost, runtime latency, and transient infrastructure failure modes.

Recommended use:

- high-impact UnityAgent PRs;
- Runtime / Context / Eval changes;
- release candidates;
- before a deliberate rebaseline;
- any change whose Production behavior needs explicit proof.

The workflow defaults to the frozen runtime comparison identity:

- model: `gpt-5.6-luna`;
- reasoning effort: `xhigh`.

It executes:

```text
Production Smoke
  → Behavior grading
  → candidate RebaselineSummary
  → Baseline Comparator --require-pass
  → upload retained candidate evidence
```

The workflow does not run Historical Replay and does not update the frozen baseline.

## Authority boundaries

Phase 10 adds no new execution authority.

```text
Runtime        executes and enforces
Persistence    stores evidence
Eval           grades current behavior
Rebaseline     aggregates candidate facts
Regression     compares already-produced facts
```

`Eval/Regression` must never:

- invoke Codex directly;
- mutate Unity/C# source;
- reconstruct changed paths from prose;
- rewrite Phase 9 evidence;
- update the frozen baseline;
- reinterpret non-Agent infrastructure failures as Agent regressions.

## Definition of Done

Phase 10 is complete when:

- the Phase 9 freeze is the only baseline authority;
- comparator schema and validator are canonical;
- strict/comparable/not-comparable/insufficient-evidence states are tested;
- PASS, regression, inconclusive and rebaseline-required decisions are tested;
- runtime timeout is proven to remain non-Agent/inconclusive;
- model/policy definition changes are proven to require rebaseline;
- source/context/Codex tooling drift remains visible but comparable;
- candidate Historical Replay is not incorrectly required;
- a manual real Production Regression Gate workflow exists;
- Phase 9 Production Smoke and Freeze contracts remain unchanged;
- all canonical CI contracts remain green.

## After Phase 10

Phase 10 completes the first quality-defense loop:

```text
Phase 8  single-repository execution authority
Phase 9  frozen Production quality baseline
Phase 10 automatic baseline comparison / regression decision
```

After this point, UnityAgent should spend time in real use before adding broader Phase 11 metrics such as first-pass quality, mutation efficiency, evidence coverage, latency, token cost, or expanded production case suites.
