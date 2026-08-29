#!/usr/bin/env python3
"""Validate canonical Context Budget v1 Golden regression boundaries."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES_PATH = ROOT / "Eval" / "Datasets" / "Golden" / "context-budget-v1.yaml"
BUDGET_PATH = ROOT / "Context" / "Budget" / "context-budget.yaml"
MATERIALIZED_SCHEMA_PATH = ROOT / "Context" / "Contracts" / "materialized-context-view.schema.yaml"
CONTEXT_CATALOG_PATH = ROOT / "Context" / "Selection" / "context-catalog.yaml"

EXPECTED_PAIRS = {
    "mutation-budget-measurement": {
        "require": "mutation_requires_within_budget",
        "forbid": "unmeasured_context_blocks_mutation",
    },
    "compression-authority": {
        "require": "non_authoritative_knowledge_may_be_summarized",
        "forbid": "authoritative_context_lossy_compression_rejected",
    },
    "soft-vs-hard-limit": {
        "require": "soft_overflow_returns_compression_required",
        "forbid": "hard_overflow_blocks_execution",
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
        budget = load(BUDGET_PATH)
        materialized_schema = load(MATERIALIZED_SCHEMA_PATH)
        context_catalog = load(CONTEXT_CATALOG_PATH)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Context Budget v1 Golden validation failed:\n- {exc}")
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

    if str(budget.get("schema_version")) != "1.0":
        errors.append("Context Budget contract must be v1.0")

    estimator = budget.get("estimator", {}) or {}
    if estimator.get("exact_model_tokenizer") is not False:
        errors.append("Context Budget estimator must not claim exact model-token accounting")
    if int(estimator.get("utf8_bytes_per_estimated_token", 0) or 0) <= 0:
        errors.append("Context Budget estimator divisor must be explicit")

    compression = budget.get("compression_policy", {}) or {}
    full_only = set(compression.get("full_only_roles", []) or [])
    for role in ("user_policy", "context_pack", "primary_skill", "task_contract", "project_fact"):
        if role not in full_only:
            errors.append(f"Authoritative role missing from full_only compression policy: {role}")
    summary_allowed = set(compression.get("semantic_summary_allowed_roles", []) or [])
    if "user_policy" in summary_allowed or "task_contract" in summary_allowed:
        errors.append("Authoritative Context must not allow semantic_summary")
    if "knowledge" not in summary_allowed:
        errors.append("Knowledge must remain an allowed semantic_summary target")

    guards = budget.get("execution_guards", {}) or {}
    for guard in (
        "mutation_requires_within_budget",
        "compression_required_must_be_resolved_before_mutation",
        "blocked_must_stop_before_mutation",
        "unmeasured_must_stop_before_mutation",
    ):
        if guards.get(guard) is not True:
            errors.append(f"Context Budget execution guard missing: {guard}")

    profiles = budget.get("profiles", {}) or {}
    for profile_id in ("tight", "standard", "wide"):
        profile = profiles.get(profile_id)
        if not isinstance(profile, dict):
            errors.append(f"Missing Context Budget profile: {profile_id}")
            continue
        context_limits = profile.get("context", {}) or {}
        soft = int(context_limits.get("soft_estimated_tokens", 0) or 0)
        hard = int(context_limits.get("hard_estimated_tokens", 0) or 0)
        if not (0 < soft < hard):
            errors.append(f"Invalid soft/hard Context Budget profile: {profile_id}")

    route_profiles = budget.get("route_profiles", {}) or {}
    for route_id in (context_catalog.get("routes", {}) or {}):
        profile_id = str(route_profiles.get(route_id, "standard"))
        if profile_id not in profiles:
            errors.append(f"{route_id}: unknown Context Budget profile {profile_id}")

    budget_report = (((materialized_schema.get("properties") or {}).get("budget_report") or {}).get("properties") or {})
    decisions = set(((budget_report.get("decision") or {}).get("enum") or []))
    expected_decisions = {"within_budget", "compression_required", "blocked", "unmeasured"}
    if decisions != expected_decisions:
        errors.append("MaterializedContextView budget_report decisions must match the canonical Context Budget runtime")
    estimator_schema = budget_report.get("estimator") or {}
    if estimator_schema.get("const") != estimator.get("id"):
        errors.append("MaterializedContextView estimator must match the canonical Context Budget estimator id")

    if errors:
        print("Context Budget v1 Golden validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"Context Budget v1 Golden validation passed: {len(cases)} cases / "
        f"{len(EXPECTED_PAIRS)} boundary pairs."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
