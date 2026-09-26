"""Performance Candidateの静的結果とContext Receiptを検証する。実測の証明ではない。"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class PerformancePilotContractError(ValueError):
    pass


REQUIRED_FIELDS = frozenset({"status", "profile_id", "capability", "confirmed_facts", "measurement_summary", "bottleneck_classification", "hypotheses", "rejected_hypotheses", "required_observations", "recommendations", "observed_evidence", "evidence_level", "known_limitations", "received_context_id", "received_context_fingerprint", "runtime_evaluation"})
METADATA_FIELDS = frozenset({"measurement_source", "unity_version", "platform", "graphics_api", "capture_mode", "build_type", "scene_or_scope", "measurement_window", "known_limitations", "validity"})
CLASSIFICATIONS = frozenset({"cpu", "gpu", "memory", "gc", "io_loading", "mixed", "unknown"})


def verify_performance_read_only(manifest: Mapping[str, Any], transported: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    """Generated、Transported、Receivedとperformance_analysisの静的契約を照合する。"""
    view = manifest.get("materialized_context")
    if not isinstance(view, Mapping) or not isinstance(view.get("specialist_context"), Mapping):
        raise PerformancePilotContractError("Performance Specialist Context is missing")
    specialist = view["specialist_context"]
    if specialist.get("profile_id") != "performance_subagent" or specialist.get("capability") != "performance.analyze":
        raise PerformancePilotContractError("Performance Specialist identity or capability is invalid")
    expected = (view.get("context_id"), (view.get("context_fingerprint") or {}).get("value"))
    if not all(isinstance(value, str) and value for value in expected):
        raise PerformancePilotContractError("generated Context identity is invalid")
    if transported.get("context_id") != expected[0] or transported.get("context_fingerprint") != expected[1] or transported.get("specialist_context") != specialist:
        raise PerformancePilotContractError("transported Specialist Context does not match generated Context")
    if not isinstance(result, Mapping) or set(result) != REQUIRED_FIELDS:
        raise PerformancePilotContractError("Performance result fields are not exact")
    if (result["received_context_id"], result["received_context_fingerprint"]) != expected:
        raise PerformancePilotContractError("received Specialist Context identity does not match generated Context")
    if result["profile_id"] != "performance_subagent" or result["capability"] != "performance.analyze":
        raise PerformancePilotContractError("Performance result identity or capability is invalid")
    if result["status"] != "completed" or result["evidence_level"] != "static" or result["runtime_evaluation"] != "NOT_EVALUATED_RUNTIME":
        raise PerformancePilotContractError("Pilot cannot claim runtime verification")
    if result["bottleneck_classification"] not in CLASSIFICATIONS:
        raise PerformancePilotContractError("bottleneck classification is invalid")
    for field in ("confirmed_facts", "hypotheses", "rejected_hypotheses", "required_observations", "recommendations", "observed_evidence", "known_limitations"):
        if not isinstance(result[field], list):
            raise PerformancePilotContractError(f"{field} must be a list")
    summary = result["measurement_summary"]
    if not isinstance(summary, Mapping) or set(summary) != {"metadata", "metrics", "baseline", "candidate", "delta"}:
        raise PerformancePilotContractError("measurement_summary shape is invalid")
    metadata = summary["metadata"]
    if not isinstance(metadata, Mapping) or set(metadata) != METADATA_FIELDS or not isinstance(metadata["known_limitations"], list):
        raise PerformancePilotContractError("measurement metadata shape is invalid")
    if metadata["validity"] not in {"not_measured", "fixture_input"}:
        raise PerformancePilotContractError("static fixture cannot claim observed runtime measurement")
    if not isinstance(summary["metrics"], list):
        raise PerformancePilotContractError("measurement metrics must be a list")
    if metadata["validity"] == "not_measured" and (summary["metrics"] or any(summary[key] is not None for key in ("baseline", "candidate", "delta")) or result["bottleneck_classification"] != "unknown" or not result["required_observations"]):
        raise PerformancePilotContractError("missing measurement requires unknown classification and observations")
    if metadata["validity"] == "fixture_input" and metadata["measurement_source"] != "fixture_input":
        raise PerformancePilotContractError("fixture values must identify their source")
    if metadata["validity"] == "not_measured" and metadata["measurement_source"] != "none":
        raise PerformancePilotContractError("missing measurement source must be none")
    for metric in summary["metrics"]:
        if not isinstance(metric, Mapping) or set(metric) != {"name", "value", "unit", "source"} or metric["source"] != "fixture_input" or not isinstance(metric["name"], str) or not metric["name"] or not isinstance(metric["value"], (int, float)) or isinstance(metric["value"], bool) or not isinstance(metric["unit"], str) or not metric["unit"]:
            raise PerformancePilotContractError("static metric must identify numeric fixture input")
    comparison_requested = any(item.get("key") == "analysis_mode" and item.get("value") == "comparison_requested" for item in specialist.get("items", []) if isinstance(item, Mapping))
    if comparison_requested and summary["baseline"] is None and not any(isinstance(item, str) and "baseline" in item.lower() for item in result["required_observations"]):
        raise PerformancePilotContractError("comparison without baseline requires baseline observation")
    if not result["observed_evidence"]:
        raise PerformancePilotContractError("performance_analysis evidence is required")
    for item in result["observed_evidence"]:
        if not isinstance(item, Mapping) or set(item) != {"type", "source_ref", "observation"} or item["type"] not in {"project_fact", "source_read", "static_review", "performance_analysis"} or not all(isinstance(item[key], str) and item[key] for key in ("source_ref", "observation")):
            raise PerformancePilotContractError("static Performance evidence is invalid")
    if not any(item["type"] == "performance_analysis" for item in result["observed_evidence"]):
        raise PerformancePilotContractError("performance_analysis evidence is required")
    return {"status": "fixture_contract_verified", "receipt_integrity": "verified", "evidence_level": "static", "runtime_evaluation": "NOT_EVALUATED_RUNTIME"}
