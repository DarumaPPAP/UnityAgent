"""Player Runtime verification without conflating Editor and target-device evidence."""
from __future__ import annotations

from typing import Any, Mapping


def _status(value: Mapping[str, Any] | None) -> str:
    if value is None:
        return "not_observed"
    return str(value.get("status") or "not_observed")


def classify_editor_player(
    *,
    editor_result: Mapping[str, Any] | None,
    player_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep Editor and Player verification states independent."""
    editor_status = _status(editor_result)
    player_status = _status(player_result)
    editor_verified = editor_status == "passed"
    player_verified = (
        player_status == "passed"
        and player_result is not None
        and player_result.get("provider_ref") == "player_runtime"
        and "player_observation" in set(player_result.get("evidence") or [])
    )

    if editor_status == "failed":
        overall = "failed"
    elif editor_verified and player_verified:
        overall = "passed"
    elif editor_verified or player_verified:
        overall = "partial"
    elif player_status in {"unavailable", "unknown", "not_observed"} or (
        player_result is not None
        and player_result.get("failure_class") in {"unavailable", "unknown", "not_observed"}
    ):
        overall = "partial"
    else:
        overall = "failed"

    return {
        "status": overall,
        "editor": {
            "status": editor_status,
            "verified": editor_verified,
            "evidence": list((editor_result or {}).get("evidence") or []),
        },
        "player": {
            "status": player_status,
            "verified": player_verified,
            "failure_class": None if player_result is None else player_result.get("failure_class"),
            "evidence": list((player_result or {}).get("evidence") or []),
        },
        "editor_pass_implies_player_pass": False,
        "verified": editor_verified and player_verified,
    }


def verify_target_performance(
    player_result: Mapping[str, Any],
    *,
    requirement: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate structured target-device samples against an explicit proof contract.

    A runtime/frame sample by itself is never target performance proof. Proof is
    only observed when the caller supplies explicit target identity, sample/duration
    floors, metric threshold, comparator, and a proof contract reference.
    """
    if player_result.get("status") != "passed":
        return {
            "status": "not_observed",
            "failure_class": player_result.get("failure_class") or "not_observed",
            "evidence_strength": "none",
            "proof_observed": False,
            "meets_target": None,
        }
    if player_result.get("evidence_class") != "target_performance_sample":
        return {
            "status": "not_observed",
            "failure_class": "not_observed",
            "evidence_strength": "runtime_observation",
            "proof_observed": False,
            "meets_target": None,
        }

    required_fields = {
        "target_device_id",
        "minimum_samples",
        "minimum_duration_seconds",
        "metric",
        "comparator",
        "threshold",
        "proof_contract_ref",
    }
    missing = sorted(required_fields - set(requirement))
    if missing:
        return {
            "status": "not_observed",
            "failure_class": "precondition_failed",
            "reason": f"performance proof requirement is incomplete: {missing}",
            "evidence_strength": "target_performance_sample",
            "proof_observed": False,
            "meets_target": None,
        }

    if player_result.get("target_device_id") != requirement.get("target_device_id"):
        return {
            "status": "not_observed",
            "failure_class": "precondition_failed",
            "reason": "Player observation target device does not match proof requirement",
            "evidence_strength": "target_performance_sample",
            "proof_observed": False,
            "meets_target": None,
        }

    payload = player_result.get("payload")
    if not isinstance(payload, Mapping):
        return {
            "status": "not_observed",
            "failure_class": "not_observed",
            "evidence_strength": "target_performance_sample",
            "proof_observed": False,
            "meets_target": None,
        }

    try:
        sample_count = int(payload.get("sample_count"))
        duration_seconds = float(payload.get("duration_seconds"))
        minimum_samples = int(requirement.get("minimum_samples"))
        minimum_duration = float(requirement.get("minimum_duration_seconds"))
    except (TypeError, ValueError):
        return {
            "status": "not_observed",
            "failure_class": "not_observed",
            "evidence_strength": "target_performance_sample",
            "proof_observed": False,
            "meets_target": None,
        }

    metrics = payload.get("metrics")
    metric_name = str(requirement.get("metric"))
    if not isinstance(metrics, Mapping) or metric_name not in metrics:
        return {
            "status": "not_observed",
            "failure_class": "not_observed",
            "evidence_strength": "target_performance_sample",
            "proof_observed": False,
            "meets_target": None,
        }
    if sample_count < minimum_samples or duration_seconds < minimum_duration:
        return {
            "status": "not_observed",
            "failure_class": "not_observed",
            "reason": "target performance sample floor was not satisfied",
            "evidence_strength": "target_performance_sample",
            "proof_observed": False,
            "meets_target": None,
            "sample_count": sample_count,
            "duration_seconds": duration_seconds,
        }

    try:
        observed = float(metrics[metric_name])
        threshold = float(requirement.get("threshold"))
    except (TypeError, ValueError):
        return {
            "status": "not_observed",
            "failure_class": "not_observed",
            "evidence_strength": "target_performance_sample",
            "proof_observed": False,
            "meets_target": None,
        }

    comparator = str(requirement.get("comparator"))
    if comparator == "<=":
        meets_target = observed <= threshold
    elif comparator == "<":
        meets_target = observed < threshold
    elif comparator == ">=":
        meets_target = observed >= threshold
    elif comparator == ">":
        meets_target = observed > threshold
    else:
        return {
            "status": "not_observed",
            "failure_class": "unsupported",
            "reason": f"unsupported performance comparator: {comparator}",
            "evidence_strength": "target_performance_sample",
            "proof_observed": False,
            "meets_target": None,
        }

    return {
        "status": "passed" if meets_target else "failed",
        "failure_class": None,
        "performance_outcome": "target_met" if meets_target else "target_missed",
        "evidence_strength": "target_performance_proof",
        "proof_observed": True,
        "meets_target": meets_target,
        "proof_contract_ref": str(requirement.get("proof_contract_ref")),
        "target_device_id": str(requirement.get("target_device_id")),
        "metric": metric_name,
        "observed": observed,
        "comparator": comparator,
        "threshold": threshold,
        "sample_count": sample_count,
        "duration_seconds": duration_seconds,
    }
