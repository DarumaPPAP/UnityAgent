# Phase 1 — Canonical Contracts

Status: implemented on `refactor/architecture-phase1-canonical-contracts`

Base: Phase 0 merge `85cf7f655d37144f24b26df5dd4fe183256f1fe1`

## Scope

Phase 1 establishes canonical structured boundary facts before moving production implementations. No `.ai` path is deleted or made non-authoritative in this phase, and no Graph repository runtime is imported yet.

## Canonical contract owners

### Runtime

- `Runtime/Contracts/execution-result.schema.yaml`
- `Runtime/Contracts/execution-evidence.schema.yaml`
- `Runtime/Contracts/mutation-evidence.schema.yaml`
- `Runtime/Contracts/runtime-failure.schema.yaml`

`ExecutionResult` owns the canonical structured representation of `changed_paths`, gate outcomes, and tool identity. `changed_paths` carries `observation_state`; `not_observed + []` is not a mutation no-op.

### Persistence

- `Persistence/Contracts/definition-fingerprint.schema.yaml`
- `Persistence/Contracts/evidence-record.schema.yaml`
- `Persistence/Contracts/execution-state.schema.yaml`
- `Persistence/Contracts/workflow-state.schema.yaml`
- `Persistence/Contracts/loop-control-state.schema.yaml`
- `Persistence/Contracts/run-checkpoint.schema.yaml`
- `Persistence/Contracts/session-record.schema.yaml`
- `Persistence/Contracts/memory-record.schema.yaml`

`LoopControlState` contains semantic loop progress only. Hard timeout/retry/turn/cost controls are intentionally absent and remain Runtime responsibilities. Memory requires source Evidence references. Checkpoint, Memory, and Evidence remain separate contracts.

### Operations

- `Operations/Observability/trace-record.schema.yaml`

Trace events are structured and evidence-linkable. This contract does not grant Operations authority to bypass Policy or Runtime enforcement.

### Eval

- `Eval/Attribution/eval-record.schema.yaml`
- `Eval/GoldenContracts/golden-contract.schema.yaml`

Infrastructure/evaluator/fixture/unavailable-evidence failures are `not_observed` and are excluded from the Agent-quality denominator. `agent_behavior_regression` is an observed Agent-quality result.

## Legacy normalization

`Eval/Replay/legacy_bundle_normalizer.py` is a migration-only adapter. It:

- consumes the existing BehaviorEval `execution-envelope.yaml` shape;
- uses structured `metrics.json.changed_paths` when present;
- never reparses diff text to derive canonical changed paths;
- marks changed paths `not_observed` when legacy evidence did not record them;
- preserves gate outcomes and executor/tool identity structurally when available;
- accepts a structured `metrics.json.failure_class` only as a typed fallback when the envelope has no typed failure;
- fails closed if envelope and metrics carry contradictory non-empty failure classes;
- treats a failed/unavailable legacy run with no typed failure class as `not_observed` instead of guessing from response/stderr text;
- maps typed Runtime failure classes without grading Agent quality;
- preserves Codex event/stderr references when the legacy envelope exposes them;
- records deterministic compatibility IDs when the legacy bundle did not contain canonical step/action IDs.

This adapter is temporary and is deleted only after native end-to-end canonical contracts replace legacy transport.

## Regression coverage

- Runtime contract tests: canonical changed-path observation and mutation-scope invariant.
- Persistence contract tests: semantic-loop/runtime-control separation and Memory evidence provenance.
- Operations contract test: structured trace/evidence linkage.
- Eval/replay tests (7): infrastructure denominator exclusion, existing legacy protocol fixture normalization, structured metrics preservation, malformed metrics fail-closed behavior, structured failure fallback, conflicting typed failures fail-closed, and untyped legacy failure exclusion.

CI entrypoint: `.github/workflows/validate-canonical-contracts.yml`.

## Actual production artifact replay

External historical Production Smoke artifacts were replayed without committing their raw bundle contents into the repository:

- `phase11-naming-04.zip`
- `phase11-mutation-03.zip`
- `production-smoke-20260827-utf8.zip`

The three archives contain six case directories in total. All six normalized outputs validate against the canonical `ExecutionResult` and `EvalRecord` schemas.

Observed migration behavior:

- Phase 1.1 bundles preserve structured `metrics.json.changed_paths` directly.
- Legacy v1.0 failed/unavailable bundles without a typed failure class remain `not_observed` and are excluded from the Agent-quality denominator.
- Text such as response/stderr timeout messages is intentionally not promoted to a typed `runtime_timeout` fact.
- Contradictory structured failure classes fail closed rather than choosing one source silently.

## Phase 1 exit assessment

- Required contract families exist next to their owning authority: yes.
- `changed_paths`, gate outcome, tool identity, Runtime failure, evidence refs, and mutation scope have canonical structured forms: yes.
- Missing changed-path evidence cannot silently become a no-op: yes.
- Existing BehaviorEval protocol fixture can normalize into canonical ExecutionResult/EvalRecord: yes.
- Six historical Production Smoke case directories normalize and validate against canonical ExecutionResult/EvalRecord: yes.
- Structured legacy metrics are preferred over diff reparsing: yes.
- Untyped legacy failures cannot silently enter the Agent-quality denominator: yes.
- Infrastructure failures are excluded from Agent-quality denominator by schema invariant: yes.
- Production implementation ownership has not been moved prematurely: yes.

Phase 2 must consume these contracts rather than introduce competing representations.
