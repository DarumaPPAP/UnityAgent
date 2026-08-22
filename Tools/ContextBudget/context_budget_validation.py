#!/usr/bin/env python3
"""Integrity validation for persisted UnityAgent Context Budget reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_budget_runtime import (
    BUDGET_CONTRACT_PATH,
    estimate_tokens,
    expected_artifacts,
    load_yaml,
    validate_budget_report,
)

EXTRA_OBSERVATION_ROLES = {"background_reference", "prior_failure", "knowledge"}


def validate_budget_integrity(
    root: Path,
    manifest: dict[str, Any],
    report: dict[str, Any],
) -> list[str]:
    errors = list(validate_budget_report(manifest, report))
    contract = load_yaml(root / BUDGET_CONTRACT_PATH)

    if report.get("contract") != BUDGET_CONTRACT_PATH.as_posix():
        errors.append("budget.contract must reference .ai/context-budget.yaml")

    route_id = str(manifest.get("task", {}).get("route", ""))
    expected_profile_id = str((contract.get("route_profiles", {}) or {}).get(route_id, ""))
    if report.get("profile") != expected_profile_id:
        errors.append(
            f"Context Budget profile does not match route: {report.get('profile')} != {expected_profile_id}"
        )

    profile = (contract.get("profiles", {}) or {}).get(expected_profile_id, {}) or {}
    expected_retrieval_limits = profile.get("retrieval", {}) or {}
    expected_context_limits = profile.get("context", {}) or {}

    estimator_contract = contract.get("estimator", {}) or {}
    estimator = report.get("estimator", {}) or {}
    if estimator.get("id") != estimator_contract.get("id"):
        errors.append("Context Budget estimator id does not match canonical contract")
    if estimator.get("exact_model_tokenizer") is not False:
        errors.append("Context Budget report must not claim exact model tokenizer accounting")
    divisor = int(estimator_contract.get("utf8_bytes_per_estimated_token", 0) or 0)
    if divisor <= 0:
        return errors + ["Canonical Context Budget estimator divisor must be > 0"]
    if estimator.get("utf8_bytes_per_estimated_token") != divisor:
        errors.append("Context Budget estimator divisor does not match canonical contract")

    expected_list = expected_artifacts(manifest)
    expected_by_id = {str(item["source_id"]): item for item in expected_list}

    artifacts = report.get("artifacts", []) or []
    if not isinstance(artifacts, list):
        return errors + ["budget.artifacts must be a list"]

    observation_contract = contract.get("retrieval_observation", {}) or {}
    compression_policy = contract.get("compression_policy", {}) or {}
    allowed_roles = set(observation_contract.get("allowed_roles", []) or [])
    allowed_modes = set(observation_contract.get("compression_modes", []) or [])
    full_only = set(compression_policy.get("full_only_roles", []) or [])
    excerpt_allowed = set(compression_policy.get("lossless_excerpt_allowed_roles", []) or [])
    summary_allowed = set(compression_policy.get("semantic_summary_allowed_roles", []) or [])

    source_ids: set[str] = set()
    artifact_by_id: dict[str, dict[str, Any]] = {}
    original_total = 0
    selected_total = 0
    estimated_total = 0
    compressed_count = 0
    compressed_modes: set[str] = set()

    for item in artifacts:
        if not isinstance(item, dict):
            errors.append("budget.artifacts entry must be a mapping")
            continue
        source_id = str(item.get("source_id", ""))
        role = str(item.get("role", ""))
        revision = str(item.get("source_revision", ""))
        if not source_id:
            errors.append("Budget artifact source_id is required")
        elif source_id in source_ids:
            errors.append(f"Duplicate Budget artifact source_id: {source_id}")
        source_ids.add(source_id)
        artifact_by_id[source_id] = item

        expected = expected_by_id.get(source_id)
        if expected is None and role not in EXTRA_OBSERVATION_ROLES:
            errors.append(f"Unexpected Budget artifact not selected by Context: {source_id}")
        elif expected is not None and role != str(expected.get("role", "")):
            errors.append(
                f"Budget artifact role mismatch: {source_id}={role}, expected={expected.get('role')}"
            )

        if role not in allowed_roles:
            errors.append(f"Unsupported Budget artifact role: {source_id}={role}")
        if not revision:
            errors.append(f"Budget artifact source_revision is required: {source_id}")

        original = item.get("original_utf8_bytes")
        selected = item.get("selected_utf8_bytes")
        estimated = item.get("estimated_tokens")
        if not isinstance(original, int) or original < 0:
            errors.append(f"Invalid original_utf8_bytes: {source_id}")
            continue
        if not isinstance(selected, int) or selected < 0 or selected > original:
            errors.append(f"Invalid selected_utf8_bytes: {source_id}")
            continue
        if expected is not None and expected.get("required") and selected == 0:
            errors.append(f"Required Context artifact cannot be dropped: {source_id}")

        expected_estimated = estimate_tokens(selected, divisor)
        if estimated != expected_estimated:
            errors.append(
                f"Budget artifact estimated_tokens mismatch: {source_id}={estimated}, expected={expected_estimated}"
            )

        compression = item.get("compression", {}) or {}
        if not isinstance(compression, dict):
            errors.append(f"Budget artifact compression must be a mapping: {source_id}")
            compression = {}
        mode = str(compression.get("mode", ""))
        if mode not in allowed_modes:
            errors.append(f"Unsupported Budget artifact compression mode: {source_id}={mode}")
        if mode != "none":
            compressed_count += 1
            compressed_modes.add(mode)
        if role in full_only and mode != "none":
            errors.append(f"Protected Context role was compressed: {source_id} ({role})")
        if mode == "none" and original != selected:
            errors.append(f"compression.mode none requires original == selected: {source_id}")
        if mode == "lossless_excerpt":
            if role not in excerpt_allowed:
                errors.append(f"lossless_excerpt is not allowed for role {role}: {source_id}")
            ranges = compression.get("selected_ranges")
            if not isinstance(ranges, list) or not ranges:
                errors.append(f"lossless_excerpt requires selected_ranges: {source_id}")
        if mode == "semantic_summary":
            if role not in summary_allowed:
                errors.append(f"semantic_summary is not allowed for role {role}: {source_id}")
            if not str(compression.get("summary_revision", "")).strip():
                errors.append(f"semantic_summary requires summary_revision: {source_id}")

        original_total += original
        selected_total += selected
        estimated_total += expected_estimated

    expected_missing = sorted(
        source_id
        for source_id, expected in expected_by_id.items()
        if not expected.get("auto_measurable") and source_id not in source_ids
    )
    required_missing = sorted(
        source_id
        for source_id, expected in expected_by_id.items()
        if expected.get("required") and source_id not in source_ids and not expected.get("auto_measurable")
    )

    coverage = report.get("coverage", {}) or {}
    missing = coverage.get("missing_observations", []) or []
    if not isinstance(missing, list):
        errors.append("budget.coverage.missing_observations must be a list")
        missing = []
    if sorted(str(item) for item in missing) != expected_missing:
        errors.append("budget.coverage.missing_observations does not match Manifest-selected sources")
    if coverage.get("expected_artifacts") != len(expected_list):
        errors.append("budget.coverage.expected_artifacts does not match Manifest-selected source count")
    if coverage.get("measured_artifacts") != len(artifacts):
        errors.append("budget.coverage.measured_artifacts does not match artifact count")

    if required_missing and report.get("decision") == "within_budget":
        errors.append("within_budget cannot omit required Project or External Context observations")

    manifest_context = manifest.get("context", {}) or {}
    expected_external_fetches = len(manifest_context.get("external_references", []) or [])
    expected_context_includes = len(manifest_context.get("context_includes", []) or [])
    expected_expansion_hops = 0
    context_pack_path = str((manifest_context.get("context_pack", {}) or {}).get("source_path", ""))
    if context_pack_path:
        context_pack = load_yaml(root / context_pack_path)
        expected_expansion_hops = int(
            (context_pack.get("limits", {}) or {}).get("context_expansion_hops", 0) or 0
        )

    retrieval = report.get("retrieval", {}) or {}
    if retrieval.get("artifacts") != len(artifacts):
        errors.append("budget.retrieval.artifacts does not match artifact count")
    if retrieval.get("original_utf8_bytes") != original_total:
        errors.append("budget.retrieval.original_utf8_bytes does not match artifact sum")
    if retrieval.get("selected_utf8_bytes") != selected_total:
        errors.append("budget.retrieval.selected_utf8_bytes does not match artifact sum")
    if retrieval.get("external_fetches") != expected_external_fetches:
        errors.append("budget.retrieval.external_fetches does not match Manifest external references")
    if retrieval.get("context_includes") != expected_context_includes:
        errors.append("budget.retrieval.context_includes does not match Manifest context includes")
    if retrieval.get("expansion_hops") != expected_expansion_hops:
        errors.append("budget.retrieval.expansion_hops does not match selected Context Pack")
    if retrieval.get("limits") != expected_retrieval_limits:
        errors.append("budget.retrieval.limits does not match canonical profile")

    context = report.get("context", {}) or {}
    if context.get("estimated_tokens") != estimated_total:
        errors.append("budget.context.estimated_tokens does not match artifact sum")
    if context.get("soft_estimated_tokens") != expected_context_limits.get("soft_estimated_tokens"):
        errors.append("budget.context.soft_estimated_tokens does not match canonical profile")
    if context.get("hard_estimated_tokens") != expected_context_limits.get("hard_estimated_tokens"):
        errors.append("budget.context.hard_estimated_tokens does not match canonical profile")

    compression_report = report.get("compression", {}) or {}
    if compression_report.get("applied") != (compressed_count > 0):
        errors.append("budget.compression.applied does not match artifacts")
    if compression_report.get("compressed_artifacts") != compressed_count:
        errors.append("budget.compression.compressed_artifacts does not match artifacts")
    if compression_report.get("saved_utf8_bytes") != original_total - selected_total:
        errors.append("budget.compression.saved_utf8_bytes does not match byte delta")
    if sorted(compression_report.get("modes", []) or []) != sorted(compressed_modes):
        errors.append("budget.compression.modes does not match artifacts")

    hard_reasons: list[str] = []
    max_artifacts = int(expected_retrieval_limits.get("max_artifacts", 0) or 0)
    max_bytes = int(expected_retrieval_limits.get("max_selected_utf8_bytes", 0) or 0)
    max_external = int(expected_retrieval_limits.get("max_external_fetches", 0) or 0)
    max_includes = int(expected_retrieval_limits.get("max_context_includes", 0) or 0)
    max_hops = int(expected_retrieval_limits.get("max_expansion_hops", 0) or 0)
    hard_token_limit = int(expected_context_limits.get("hard_estimated_tokens", 0) or 0)
    soft_token_limit = int(expected_context_limits.get("soft_estimated_tokens", 0) or 0)

    if len(artifacts) > max_artifacts:
        hard_reasons.append("max_artifacts_exceeded")
    if selected_total > max_bytes:
        hard_reasons.append("max_selected_utf8_bytes_exceeded")
    if expected_external_fetches > max_external:
        hard_reasons.append("max_external_fetches_exceeded")
    if expected_context_includes > max_includes:
        hard_reasons.append("max_context_includes_exceeded")
    if expected_expansion_hops > max_hops:
        hard_reasons.append("max_expansion_hops_exceeded")
    if estimated_total > hard_token_limit:
        hard_reasons.append("hard_estimated_tokens_exceeded")

    if hard_reasons:
        expected_decision = "blocked"
    elif expected_missing:
        expected_decision = "unmeasured"
    elif estimated_total > soft_token_limit:
        expected_decision = "compression_required"
    else:
        expected_decision = "within_budget"

    if report.get("decision") != expected_decision:
        errors.append(
            f"Context Budget decision mismatch: {report.get('decision')} != {expected_decision}"
        )
    if sorted(report.get("blocking_reasons", []) or []) != sorted(hard_reasons):
        errors.append("Context Budget blocking_reasons do not match recomputed hard-limit reasons")

    return errors
