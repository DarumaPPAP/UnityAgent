"""Evaluate whether evidence justifies expanding beyond Context Explorer."""

from __future__ import annotations

from typing import Any


THRESHOLDS = {
    "context_file_read_reduction": 0.30,
    "total_token_reduction": 0.30,
    "verifier_quality_delta": 0.0,
    "missed_dependency_delta": 0.0,
    "user_policy_loss": 0,
    "unverified_success_claims": 0,
    "stale_index": 0,
}


def evaluate_expansion_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    required_comparison = ("same_task", "same_source_revision", "same_acceptance_criteria")
    missing = [key for key in required_comparison if metrics.get(key) is not True]
    missing.extend(key for key in THRESHOLDS if key not in metrics)
    if missing:
        return {
            "decision": "DEFER",
            "evidence_status": "unavailable",
            "reasons": sorted(set(missing)),
            "expansion_enabled": False,
        }

    failures: list[str] = []
    if metrics["context_file_read_reduction"] < THRESHOLDS["context_file_read_reduction"]:
        failures.append("context_file_read_reduction")
    if metrics["total_token_reduction"] < THRESHOLDS["total_token_reduction"]:
        failures.append("total_token_reduction")
    if metrics["verifier_quality_delta"] < THRESHOLDS["verifier_quality_delta"]:
        failures.append("verifier_quality_delta")
    if metrics["missed_dependency_delta"] < THRESHOLDS["missed_dependency_delta"]:
        failures.append("missed_dependency_delta")
    for key in ("user_policy_loss", "unverified_success_claims", "stale_index"):
        if metrics[key] > THRESHOLDS[key]:
            failures.append(key)
    return {
        "decision": "DEFER" if failures else "ADOPT",
        "evidence_status": "passed" if not failures else "failed",
        "reasons": failures,
        "expansion_enabled": not failures,
    }
