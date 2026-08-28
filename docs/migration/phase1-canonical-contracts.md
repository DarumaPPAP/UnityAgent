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
- maps Runtime failure classes without grading Agent quality;
- fails closed on malformed/contradictory structured facts;
- records deterministic compatibility IDs when the legacy bundle did not contain canonical step/action IDs.

This adapter is temporary and is deleted only after native end-to-end canonical contracts replace legacy transport.

## Regression coverage

- Runtime contract tests: canonical changed-path observation and mutation-scope invariant.
- Persistence contract tests: semantic-loop/runtime-control separation and Memory evidence provenance.
- Operations contract test: structured trace/evidence linkage.
- Eval/replay tests: infrastructure denominator exclusion, existing legacy protocol fixture normalization, structured metrics preservation, malformed metrics fail-closed behavior.

CI entrypoint: `.github/workflows/validate-canonical-contracts.yml`.

## Phase 1 exit assessment

- Required contract families exist next to their owning authority: yes.
- `changed_paths`, gate outcome, tool identity, Runtime failure, evidence refs, and mutation scope have canonical structured forms: yes.
- Missing changed-path evidence cannot silently become a no-op: yes.
- Historical existing BehaviorEval protocol fixture can normalize into canonical ExecutionResult/EvalRecord: yes.
- Structured legacy metrics are preferred over diff reparsing: yes.
- Infrastructure failures are excluded from Agent-quality denominator by schema invariant: yes.
- Production implementation ownership has not been moved prematurely: yes.

Phase 2 must consume these contracts rather than introduce competing representations.
