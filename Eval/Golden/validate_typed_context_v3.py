#!/usr/bin/env python3
"""Validate Typed Context supplemental Golden Regression boundaries against canonical Context contracts."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "Eval" / "Datasets" / "Golden" / "typed-context-v3.yaml"
PACK_SCHEMA_PATH = ROOT / "Context" / "Contracts" / "context-pack.schema.yaml"
PROJECT_FACT_SCHEMA_PATH = ROOT / "Context" / "Contracts" / "project-fact-observation.schema.yaml"
MANIFEST_SCHEMA_PATH = ROOT / "Context" / "Manifest" / "context-manifest.schema.yaml"

EXPECTED_PAIRS = {
    "project-fact-freshness": {
        "forbid": "previous_current_fact_revalidation_required",
        "require": "current_fact_checked_at_current_attempt",
    },
    "context-include-vs-handoff": {
        "forbid": "context_include_preserves_primary_route",
        "require": "route_handoff_changes_primary_ownership",
    },
}


def load(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ValueError(f"Expected mapping: {path}")
    return document


def main() -> int:
    errors: list[str] = []
    try:
        suite = load(CASES_PATH)
        pack_schema = load(PACK_SCHEMA_PATH)
        project_fact_schema = load(PROJECT_FACT_SCHEMA_PATH)
        manifest_schema = load(MANIFEST_SCHEMA_PATH)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Typed Context Golden validation failed:\n- {exc}")
        return 1

    cases = suite.get("cases", [])
    if not isinstance(cases, list):
        errors.append("cases must be a list.")
        cases = []

    pairs: dict[str, dict[str, dict]] = defaultdict(dict)
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            errors.append("Golden case must be a mapping.")
            continue
        case_id = str(case.get("id", ""))
        if not case_id:
            errors.append("Golden case id is required.")
        elif case_id in ids:
            errors.append(f"Duplicate Golden case id: {case_id}")
        ids.add(case_id)
        pair_id = str(case.get("pair_id", ""))
        boundary = str(case.get("boundary", ""))
        if boundary not in {"require", "forbid"}:
            errors.append(f"{case_id}: invalid boundary {boundary}")
        if case.get("kind") != "regression":
            errors.append(f"{case_id}: kind must be regression")
        expectation = case.get("expectation", {})
        if not isinstance(expectation, dict):
            errors.append(f"{case_id}: expectation must be a mapping")
            continue
        if expectation.get("outcome") != "passed":
            errors.append(f"{case_id}: expected outcome must be passed")
        graders = case.get("graders", []) or []
        if not any(isinstance(item, dict) and item.get("type") == "deterministic" for item in graders):
            errors.append(f"{case_id}: deterministic grader is required")
        pairs[pair_id][boundary] = case

    for pair_id, expected in EXPECTED_PAIRS.items():
        actual = pairs.get(pair_id, {})
        if set(actual) != {"require", "forbid"}:
            errors.append(f"{pair_id}: require/forbid boundary pair is incomplete")
            continue
        for boundary, signal in expected.items():
            signals = set(actual[boundary].get("expectation", {}).get("required_signals", []) or [])
            if signal not in signals:
                errors.append(f"{pair_id}:{boundary} missing required signal {signal}")

    defs = pack_schema.get("$defs", {}) or {}
    for required_type in ("binding", "repository_reference", "external_reference", "context_include", "route_handoff"):
        if required_type not in defs:
            errors.append(f"Canonical Context Pack schema missing typed entry: {required_type}")
    invariants = pack_schema.get("x-unityagent-invariants", {}) or {}
    for invariant in ("scalar_context_entries_forbidden", "context_include_does_not_change_primary_route", "route_handoff_changes_primary_ownership"):
        if invariants.get(invariant) is not True:
            errors.append(f"Canonical Context Pack invariant missing: {invariant}")

    fact_invariants = project_fact_schema.get("x-unityagent-invariants", {}) or {}
    for invariant in (
        "current_requires_checked_at_current_manifest_attempt",
        "checked_at_attempt_must_not_precede_observed_at_attempt",
        "observed_at_attempt_must_not_exceed_manifest_attempt",
        "retry_requires_explicit_reobservation_or_revalidation",
    ):
        if fact_invariants.get(invariant) is not True:
            errors.append(f"Canonical Project Fact invariant missing: {invariant}")

    manifest_rules = manifest_schema.get("x-unityagent-rules", {}) or {}
    for rule in (
        "current_project_fact_requires_checked_at_attempt_equal_manifest_attempt",
        "project_fact_checked_at_attempt_must_not_precede_observed_at_attempt",
        "project_fact_observed_at_attempt_must_not_exceed_manifest_attempt",
        "retry_requires_explicit_project_fact_reobservation_or_revalidation",
    ):
        if manifest_rules.get(rule) is not True:
            errors.append(f"Canonical Context Manifest rule missing: {rule}")
    project_facts = ((manifest_schema.get("properties") or {}).get("project_facts") or {})
    item_ref = (project_facts.get("items") or {}).get("$ref")
    if item_ref != "urn:unityagent:context:project-fact-observation":
        errors.append("Context Manifest project_facts must reference the canonical ProjectFactObservation contract")

    if errors:
        print("Typed Context Golden validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Typed Context Golden validation passed: {len(cases)} cases / {len(EXPECTED_PAIRS)} boundary pairs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
