# Phase 10 — Baseline Comparator / Regression Gate

Status: implemented; local Production gate is the standard operating path  
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

## Operating model

Phase 10 has one canonical comparison contract and two execution front ends.

```text
                         Frozen Phase 9 Baseline
                                  │
                                  ▼
                         Regression Gate Core
                                  │
                       ┌──────────┴──────────┐
                       │                     │
                       ▼                     ▼
              Local Production Gate   GitHub-hosted Gate
                 STANDARD                OPTIONAL
                       │                     │
          local Codex CLI session      OPENAI_API_KEY
          ChatGPT-authenticated        repository secret
                       │                     │
                       └──────────┬──────────┘
                                  ▼
                         Same Comparator
                                  ▼
             PASS / BLOCK / REBASELINE_REQUIRED
```

The standard path is local because UnityAgent development already occurs on the user's machine and the local Codex CLI can reuse its existing authenticated ChatGPT session. Phase 10 itself does not require `OPENAI_API_KEY`.

The GitHub-hosted workflow is retained only as an explicit CI option for future fully automated execution.

## Baseline authority

Phase 10 does not create a second baseline.

The only baseline authority remains:

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

## Standard local Production Regression Gate

Canonical entry point:

`Tools/Phase10/run_local_regression_gate.py`

Default runtime identity intentionally matches the frozen Phase 9 baseline:

- model: `gpt-5.6-luna`;
- reasoning effort: `xhigh`;
- per-case timeout: `600` seconds.

Normal PowerShell invocation from the UnityAgent repository root:

```powershell
python .\Tools\Phase10\run_local_regression_gate.py
```

An explicit immutable run ID may be supplied when desired:

```powershell
python .\Tools\Phase10\run_local_regression_gate.py `
  --run-id phase10-local-20260830-01 `
  --model gpt-5.6-luna `
  --reasoning-effort xhigh `
  --timeout-seconds 600
```

The local runner performs this pipeline:

```text
Validate Phase 9 Freeze
        ↓
Verify clean Git worktree
        ↓
Record current HEAD revision
        ↓
Find local Codex CLI + record version
        ↓
Remove OPENAI_API_KEY from child environment
        ↓
Production Smoke (4 canonical cases)
        ↓
Behavior Eval
        ↓
Candidate RebaselineSummary
        ↓
Baseline Comparator --require-pass
        ↓
baseline-comparison.json
```

### Local authentication boundary

The local runner does not create, read, print, persist, or require an OpenAI API key.

If `OPENAI_API_KEY` happens to exist in the parent shell, the runner removes it from the Production Smoke child environment before Codex is launched. This prevents the standard path from silently switching to API-key billing.

Codex authentication remains owned by the local Codex CLI installation. If that CLI is not authenticated, Runtime execution will fail and Phase 10 will remain inconclusive rather than inventing a quality result.

The local runner does not perform a separate synthetic LLM authentication probe because that would itself consume an execution and would duplicate the real Production observation.

### Local provenance boundary

A local candidate must have a clean Git worktree before execution.

This is required because `source_revision` must truthfully identify the source that produced the candidate behavior. Generated evidence under ignored `Artifacts/` does not make the worktree dirty.

The runner records:

- current Git branch;
- current 40-character HEAD revision;
- clean-worktree state;
- Codex executable path;
- Codex version;
- local execution mode;
- whether an inherited `OPENAI_API_KEY` value was removed.

The metadata is retained at:

`Artifacts/ProductionSmoke/<run-id>/local-gate-metadata.json`

## Candidate input

The Phase 10 comparator consumes the existing Phase 9 `RebaselineSummary` generated from a new Production Smoke run:

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

A clean candidate may remain:

`RebaselineSummary.status = smoke_passed_pending_historical`

and still pass Phase 10 if current Production behavior is fully observed and comparable.

Historical Replay becomes mandatory again only when a candidate is proposed as a new frozen baseline.

## Comparability first

A candidate must not be called a regression until the comparator establishes that the baseline and candidate use a compatible evaluation/runtime definition.

### `strict_comparable`

No tracked comparison drift is present.

### `comparable_with_drift`

The evaluation contract is stable while expected implementation/tooling facts changed.

Informational drift includes:

- source revision;
- Codex CLI version;
- per-case `context_revision`.

These facts remain visible but do not by themselves block quality comparison.

### `not_comparable`

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

### `insufficient_evidence`

Missing canonical comparison evidence, such as a per-case DefinitionFingerprint, produces:

`BLOCK_INCONCLUSIVE`

Missing comparison evidence is not treated as Agent regression and is never silently accepted.

## Gate decisions

| Decision | Meaning | Merge guidance |
| --- | --- | --- |
| `PASS` | Comparable candidate meets the frozen Production baseline | May proceed |
| `BLOCK_REGRESSION` | Fully observed Agent behavior is worse than the frozen baseline | Block / investigate |
| `BLOCK_INCONCLUSIVE` | Production quality could not be fully established | Block / repair or rerun |
| `REBASELINE_REQUIRED` | Evaluation/runtime definition changed | Review definition change; do not call it regression |

Decision order:

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

An Agent regression requires observed Agent behavior:

```text
observation_state = observed
quality_denominator_eligible = true
status = failed
```

or an active canonical `agent_behavior_regression`.

A lower fully-observed quality result than the frozen 4/4 baseline is also a regression.

The following remain non-Agent / inconclusive:

- `runtime_timeout`;
- `runtime_protocol_failure`;
- `runtime_cancelled`;
- `runtime_tool_unavailable`;
- `runtime_permission_denied`;
- `evaluator_contract_failure`;
- `task_fixture_invalid`;
- `unavailable_required_evidence`.

## Output artifacts

Each local run retains the ordinary Phase 9/10 evidence under:

`Artifacts/ProductionSmoke/<run-id>/`

including:

- `execution-summary.json`;
- per-case Runtime/Persistence/Eval evidence;
- `eval-summary.json`;
- `rebaseline-summary.json`;
- `baseline-comparison.json`;
- `local-gate-metadata.json`.

Inspect the final report in PowerShell with explicit UTF-8:

```powershell
Get-Content ".\Artifacts\ProductionSmoke\<run-id>\baseline-comparison.json" -Raw -Encoding UTF8
```

## Comparator-only CLI

If a candidate RebaselineSummary already exists, no LLM execution is required to compare it:

```powershell
python .\Eval\Regression\compare_baseline.py `
  --baseline ".\Eval\Rebaseline\Baselines\phase9-baseline-20260830-09.yaml" `
  --candidate ".\Artifacts\ProductionSmoke\<run-id>\rebaseline-summary.json" `
  --output ".\Artifacts\ProductionSmoke\<run-id>\baseline-comparison.json" `
  --require-pass
```

Gate-specific exit codes:

- `0` — PASS;
- `10` — BLOCK_REGRESSION;
- `11` — BLOCK_INCONCLUSIVE;
- `12` — REBASELINE_REQUIRED;
- `20` — invalid input/contract/comparison failure.

## Optional GitHub-hosted CI gate

`.github/workflows/baseline-regression-gate.yml` is intentionally `workflow_dispatch` only and is **not the standard Phase 10 operating path**.

It is retained for cases where fully automated GitHub-hosted execution is intentionally desired. Because a fresh GitHub-hosted runner has no user's local ChatGPT/Codex session, this optional path currently requires an `OPENAI_API_KEY` repository secret.

Recommended optional use:

- release automation when API-backed CI is intentionally enabled;
- centralized unattended regression checks;
- future service-account/CI authentication work.

A failure at that workflow's credential preflight is `BLOCKED_NOT_RUN`; it does not mean Phase 10, Codex quality, or the comparator regressed.

The failed run `33301195983` is therefore retained as infrastructure evidence and is not a quality candidate.

## Authority boundaries

Phase 10 adds no new execution authority.

```text
Runtime        executes and enforces
Persistence    stores evidence
Eval           grades current behavior
Rebaseline     aggregates candidate facts
Regression     compares already-produced facts
Local runner   orchestrates existing authorities only
```

The local runner must never:

- grade Agent quality itself;
- rewrite Phase 9 evidence;
- update the frozen baseline;
- reconstruct changed paths from prose;
- reinterpret infrastructure failures as Agent regressions.

## Definition of Done

Phase 10 is complete when:

- the Phase 9 freeze is the only baseline authority;
- comparator schema and validator are canonical;
- all four gate decisions are tested;
- non-Agent failures remain inconclusive;
- model/policy definition changes require rebaseline;
- source/context/Codex tooling drift remains visible but comparable;
- candidate Historical Replay is not incorrectly required;
- the standard local runner exists and uses the local Codex session without requiring an API key;
- the local runner records clean source provenance and uses the same canonical Phase 10 comparator;
- the GitHub-hosted API-backed gate remains optional;
- Phase 9 Production Smoke and Freeze contracts remain unchanged;
- all canonical CI contracts remain green;
- one real local `gpt-5.6-luna / xhigh` candidate reaches `gate.decision = PASS`.

## After Phase 10

After the first real local PASS, the UnityAgent quality-defense loop v1 is complete:

```text
Phase 8  single-repository execution authority
Phase 9  frozen Production quality baseline
Phase 10 local/optional-CI regression decision
```

At that point, prefer real usage and observation before adding broader Phase 11 metrics.
