# Phase 9 — Baseline Freeze

Status: freeze candidate for reviewed merge  
Canonical repository: `DarumaPPAP/UnityAgent`

## Purpose

This document records how a `baseline_ready` Phase 9 result becomes a repository-reviewed baseline without rewriting or copying mutable execution evidence into the baseline definition.

The freeze is a reference contract, not a new Production Smoke run and not a second evaluator.

```text
immutable Production Smoke evidence
        ↓
RebaselineSummary = baseline_ready
        ↓
reviewed BaselineFreeze manifest
        ↓
future comparison anchor
```

## Accepted candidate

The dedicated freeze manifest is:

`Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml`

It records:

- Production Smoke run `phase9-baseline-20260830-09`;
- execution source revision `08d915886a24689e40cc74b1d32277bb80a3aa5a`;
- model `gpt-5.6-luna`;
- reasoning effort `xhigh`;
- Codex CLI `0.150.1`;
- 4/4 observed, denominator-eligible Production cases;
- regression pass rate `1.0`;
- ARCH/NAMING/MUTATION/EVIDENCE historical replay coverage;
- all four canonical DefinitionFingerprints;
- immutable references to the run-local RebaselineSummary and Historical Replay artifacts.

The source revision intentionally remains the revision that actually executed the accepted Production Smoke. It must not be replaced with the later commit that introduces this freeze manifest.

## Historical replay semantics

The accepted historical replay has:

`quality_denominator_eligible_count = 0`

This value is retained explicitly rather than hidden or rewritten.

Under the Phase 9 contract, Historical Replay is a compatibility/provenance coverage requirement. Its baseline gate is coverage of all four namespaces:

- ARCH
- NAMING
- MUTATION
- EVIDENCE

Therefore the frozen manifest declares:

`quality_semantics: namespace_coverage_only`

This does not upgrade legacy `not_observed` cases into quality evidence and does not change the current Production quality denominator. The Production quality claim remains the independently observed 4/4 `phase9-baseline-20260830-09` run.

Any future phase that wants historical replay quality eligibility to become a baseline gate must introduce that as a reviewed contract change rather than silently reinterpret this Phase 9 freeze.

## Freeze invariants

The BaselineFreeze contract requires:

1. `rebaseline_status = baseline_ready`.
2. Production execution was observed.
3. Production quality is exactly 4/4 with regression pass rate 1.0.
4. Historical Replay contains exactly ARCH/NAMING/MUTATION/EVIDENCE namespace coverage.
5. All four canonical DefinitionFingerprints are retained.
6. Provenance references resolve conceptually to the accepted run ID and cannot point to another run.
7. Execution evidence remains immutable.
8. Freeze is performed only as a reviewed repository change.

`Eval/Rebaseline/validate_baseline_freeze.py` and `Eval/Tests/test_phase9_baseline_freeze.py` enforce these invariants.

## Evidence boundary

The freeze manifest does not claim that its referenced `Artifacts/ProductionSmoke/...` files are committed to Git. Those files remain retained execution evidence in the Production Smoke artifact store/workspace.

The manifest freezes their canonical run-relative references and the values reviewed from the `baseline_ready` summary. It must not regenerate, repair, normalize, or overwrite those files.

## UTF-8

UnityAgent text contracts, YAML, JSON, Markdown, Python text I/O, and verification output are UTF-8. Validators read repository text with explicit `encoding="utf-8"`.

Windows/PowerShell inspection must likewise use explicit UTF-8 handling where the host defaults are ambiguous, for example:

```powershell
Get-Content <path> -Raw -Encoding UTF8
```

Encoding display problems must never be treated as evidence corruption until the underlying UTF-8 file has been checked directly.

## Review checklist

Before merge, verify:

- the manifest run ID is `phase9-baseline-20260830-09`;
- the source revision is the execution revision, not the freeze branch revision;
- Runtime identity matches the accepted RebaselineSummary;
- the four Production cases remain 4/4 observed passes;
- canonical failure taxonomy remains clean;
- all four DefinitionFingerprints match the accepted summary;
- Historical Replay retains the recorded `quality_denominator_eligible_count = 0` transparently;
- no Production Smoke evidence was rewritten;
- CI validates the checked-in freeze manifest.

After merge, the manifest becomes the Phase 9 comparison anchor. A future baseline must be added as a new reviewed freeze rather than rewriting this accepted record in place.
