#!/usr/bin/env python3
"""Validate Context Budget v1 supplemental Golden Regression boundaries."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "Tests" / "GoldenTasks" / "context-budget-v1.yaml"
BUDGET_PATH = ROOT / ".ai" / "context-budget.yaml"
INDEX_PATH = ROOT / ".ai" / "context-index.yaml"
MANIFEST_SCHEMA_PATH = ROOT / ".ai" / "context-manifest.schema.yaml"

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
        index = load(INDEX_PATH)
        manifest_schema = load(MANIFEST_SCHEMA_PATH)
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

    rules = index.get("routing_rules", {}) or {}
    for rule in (
        "context_budget_required_before_mutation",
        "estimated_context_tokens_are_not_exact_provider_tokens",
        "project_and_external_budget_observation_required",
        "authoritative_context_lossy_compression_forbidden",
        "hard_context_budget_overflow_stops_mutation",
    ):
        if rules.get(rule) is not True:
            errors.append(f"Canonical routing rule missing: {rule}")

    if index.get("context_budget") != ".ai/context-budget.yaml":
        errors.append("context-index must bind .ai/context-budget.yaml")

    extensions = manifest_schema.get("extensions", {}) or {}
    if str(extensions.get("context_budget")) != "1.0":
        errors.append("Context Manifest must declare Context Budget extension v1.0")
    budget_rules = manifest_schema.get("budget_rules", {}) or {}
    if budget_rules.get("mutation_requires_within_budget") is not True:
        errors.append("Context Manifest budget rules must block non-budgeted mutation")

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
