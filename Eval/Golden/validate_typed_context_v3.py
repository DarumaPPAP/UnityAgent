#!/usr/bin/env python3
"""Validate Typed Context v3 supplemental Golden Regression boundaries."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "Tests" / "GoldenTasks" / "typed-context-v3.yaml"
INDEX_PATH = ROOT / ".ai" / "context-index.yaml"
PACK_SCHEMA_PATH = ROOT / ".ai" / "context-pack.schema.yaml"
MANIFEST_SCHEMA_PATH = ROOT / ".ai" / "context-manifest.schema.yaml"

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
        index = load(INDEX_PATH)
        pack_schema = load(PACK_SCHEMA_PATH)
        manifest_schema = load(MANIFEST_SCHEMA_PATH)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Typed Context v3 Golden validation failed:\n- {exc}")
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

    rules = index.get("routing_rules", {}) or {}
    for rule in (
        "scalar_context_entries_forbidden",
        "context_include_does_not_change_primary_route",
        "route_handoff_changes_primary_route",
        "project_fact_provenance_required",
        "current_project_fact_requires_current_attempt_check",
        "retry_must_not_implicitly_reuse_project_facts",
    ):
        if rules.get(rule) is not True:
            errors.append(f"Canonical routing rule missing: {rule}")

    if str(pack_schema.get("schema_version")) != "3.0":
        errors.append("Context Pack contract must be v3.0")
    if str(manifest_schema.get("schema_version")) != "3.1":
        errors.append("Context Manifest schema must be v3.1")

    typed_context = pack_schema.get("typed_context", {}) or {}
    allowed_types = set(typed_context.get("allowed_types", []) or [])
    for required_type in (
        "binding",
        "repository_reference",
        "external_reference",
        "context_include",
        "route_handoff",
    ):
        if required_type not in allowed_types:
            errors.append(f"Typed Context contract missing type: {required_type}")

    fact_rules = manifest_schema.get("project_fact_rules", {}) or {}
    if fact_rules.get("current_requires_checked_at_attempt_equal_manifest_attempt") is not True:
        errors.append("Manifest schema does not enforce current-attempt freshness")
    if fact_rules.get("retry_requires_explicit_reobservation_or_revalidation") is not True:
        errors.append("Manifest schema does not require retry Fact revalidation")

    if errors:
        print("Typed Context v3 Golden validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Typed Context v3 Golden validation passed: {len(cases)} cases / {len(EXPECTED_PAIRS)} boundary pairs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
