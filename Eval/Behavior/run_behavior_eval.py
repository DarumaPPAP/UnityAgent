#!/usr/bin/env python3
"""Canonical Actual Behavior Eval entrypoint.

The mature Phase-11 runner is retained as an implementation core under Eval,
while this entrypoint switches its data authority to Eval/Datasets. Golden
expectations remain evaluator-only and are never added to Runtime requests.
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEHAVIOR_DIR = ROOT / "Eval" / "Behavior"
for path in (ROOT, BEHAVIOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import core_run_behavior_eval as core  # noqa: E402
import normalize_result as normalizer  # noqa: E402
from Eval.Datasets.paths import (  # noqa: E402
    BEHAVIOR_ROOT,
    GOLDEN_ROOT,
    canonicalize_document,
    legacy_fixture_shadow,
)

core.SUITES_PATH = BEHAVIOR_ROOT / "suites.yaml"
core.CASES_PATH = GOLDEN_ROOT / "cases.yaml"
core.PRODUCTION_CONTRACTS_PATH = BEHAVIOR_ROOT / "production-smoke-contracts.yaml"
core.GOLDEN_RUNNER = ROOT / "Eval" / "Golden" / "run_golden_evals.py"
normalizer.GOLDEN_CASES = GOLDEN_ROOT / "cases.yaml"
normalizer.BEHAVIOR_SUITES = BEHAVIOR_ROOT / "suites.yaml"

_core_load_yaml = core.load_yaml
_normalizer_load_yaml = normalizer.load_yaml
_core_validate_request = core.validate_request


def _canonical_core_load_yaml(path: Path) -> dict:
    value = _core_load_yaml(path)
    if BEHAVIOR_ROOT in path.resolve().parents or path.resolve() == BEHAVIOR_ROOT:
        return canonicalize_document(value)
    if GOLDEN_ROOT in path.resolve().parents or path.resolve() == GOLDEN_ROOT:
        return canonicalize_document(value)
    return value


def _canonical_normalizer_load_yaml(path: Path) -> dict:
    value = _normalizer_load_yaml(path)
    if BEHAVIOR_ROOT in path.resolve().parents or GOLDEN_ROOT in path.resolve().parents:
        return canonicalize_document(value)
    return value


def _canonical_validate_request(request: dict, *, suite_id: str) -> None:
    # The Phase-11 validator hard-codes Tests/BehaviorEval/Fixtures. Validate a
    # shadow against that read-only compatibility copy while preserving the
    # canonical Eval/Datasets fixture ref in the real Runtime request.
    shadow = deepcopy(request)
    workspace = shadow.get("workspace") or {}
    if isinstance(workspace, dict):
        workspace["fixture"] = legacy_fixture_shadow(str(workspace.get("fixture") or ""))
    _core_validate_request(shadow, suite_id=suite_id)


core.load_yaml = _canonical_core_load_yaml
normalizer.load_yaml = _canonical_normalizer_load_yaml
core.validate_request = _canonical_validate_request


def main() -> int:
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
