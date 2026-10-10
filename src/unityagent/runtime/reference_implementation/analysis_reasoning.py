"""Graphics / PerformanceのReasoning Artifactを観測Contextと照合する。"""
from __future__ import annotations
from unityagent.resources import resource_root

import json
import math
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, ValidationError


class AnalysisContractError(ValueError):
    pass


class AnalysisContextError(AnalysisContractError):
    pass


def _bound_observations(manifest: Mapping[str, Any], result: Mapping[str, Any], schema_name: str, *, runtime_observed: bool) -> dict[str, dict[str, Any]]:
    if not runtime_observed:
        raise AnalysisContractError("production analysis requires an observed reasoning execution")
    schema = json.loads((resource_root() / "src/unityagent/runtime/contracts" / schema_name).read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(result)
    except ValidationError as exc:
        raise AnalysisContractError(f"analysis output schema: {exc.message}") from exc
    view = manifest.get("materialized_context") or {}
    specialist = view.get("specialist_context") or {}
    if any(specialist.get(key) != result[key] for key in ("profile_id", "capability", "execution_mode", "provider_resolution")):
        raise AnalysisContextError("analysis identity differs from selected Specialist src/unityagent/context")
    expected = (view.get("context_id"), (view.get("context_fingerprint") or {}).get("value"))
    if not all(isinstance(item, str) and item for item in expected) or (result["source_context_id"], result["source_context_fingerprint"]) != expected:
        raise AnalysisContextError("source Context identity or fingerprint mismatch")
    observations = {}
    for item in specialist.get("items", []):
        if item.get("type") == "project_fact" and str(item.get("key", "")).startswith("observation:"):
            source, value = item.get("source"), item.get("value")
            if not isinstance(source, str) or not source.startswith("evidence:") or source in observations or not isinstance(value, dict) or not isinstance(value.get("result"), dict):
                raise AnalysisContextError("observation context is not uniquely evidence-bound")
            observations[source] = value
    for fact in result["confirmed_facts"]:
        if fact["source_ref"] not in observations:
            raise AnalysisContractError("confirmed fact references an unobserved source")
    return observations


def verify_graphics_analysis(manifest: Mapping[str, Any], result: Mapping[str, Any], *, runtime_observed: bool = False) -> dict[str, Any]:
    observations = _bound_observations(manifest, result, "graphics-analysis-result.schema.json", runtime_observed=runtime_observed)
    references = set(result["observation_refs"])
    if not references.issubset(observations):
        raise AnalysisContractError("graphics analysis references an unobserved source")
    supported = {observations[reference]["capability"] for reference in references}
    if not {"project.inspect", "source.read"}.issubset(supported):
        raise AnalysisContractError("graphics analysis requires project and source observations")
    if result["proposed_diff"] is not None and result["required_approval"] != "required_before_apply":
        raise AnalysisContractError("proposed diff requires approval before apply")
    return {"status": "runtime_contract_verified", "evidence_type": "graphics_diagnosis", "evidence_level": "runtime_reasoning", "runtime_evaluation": "RUNTIME_OBSERVED"}


def _metrics(values: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics = {}
    for item in values:
        value = item["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or item["name"] in metrics:
            raise AnalysisContractError("measurement must have unique metrics with finite numeric values")
        metrics[item["name"]] = item
    return metrics


def verify_performance_analysis(manifest: Mapping[str, Any], result: Mapping[str, Any], *, runtime_observed: bool = False) -> dict[str, Any]:
    observations = _bound_observations(manifest, result, "performance-analysis-result.schema.json", runtime_observed=runtime_observed)
    captures = {}
    for reference, observation in observations.items():
        if observation.get("capability") != "profiler.observe":
            continue
        for capture in observation["result"].get("measurements", []):
            if not isinstance(capture, dict) or not isinstance(capture.get("capture_id"), str):
                raise AnalysisContractError("invalid measurement observation")
            key = (reference, capture["capture_id"])
            if key in captures:
                raise AnalysisContractError("ambiguous capture identity")
            captures[key] = capture
    selected = {}
    for measurement in result["measurements"]:
        key = (measurement["source_ref"], measurement["capture_id"])
        value = {name: measurement[name] for name in ("capture_id", "metadata", "metrics")}
        if key in selected or captures.get(key) != value:
            raise AnalysisContractError("measurement values or metadata differ from observed capture")
        _metrics(value["metrics"])
        selected[key] = value
    categories = set()
    for basis in result["classification_basis"]:
        key = (basis["source_ref"], basis["capture_id"])
        measured = selected.get(key)
        if not measured or measured["metadata"]["validity"] != "valid":
            raise AnalysisContractError("classification requires a valid observed capture")
        metadata = measured["metadata"]
        if any(metadata[field].strip().lower() in {"unknown", "none", "not_observed"} for field in ("measurement_source", "unity_version", "platform", "graphics_api", "capture_mode", "build_type", "scene_or_scope", "measurement_window")):
            raise AnalysisContractError("classification requires known measurement conditions")
        metrics = _metrics(measured["metrics"])
        if not set(basis["metric_names"]).issubset(metrics):
            raise AnalysisContractError("classification references an unobserved metric")
        categories.update(metrics[name]["category"] for name in basis["metric_names"])
    classification = result["bottleneck_classification"]
    if classification == "mixed" and len(categories) < 2 or classification not in {"unknown", "mixed"} and classification not in categories:
        raise AnalysisContractError("bottleneck classification lacks matching measured evidence")
    if classification == "unknown" and not result["required_observations"]:
        raise AnalysisContractError("unknown classification requires further observations")
    comparison = result["comparison"]
    if comparison is not None:
        keys = [(comparison[name]["source_ref"], comparison[name]["capture_id"]) for name in ("baseline", "candidate")]
        if keys[0] == keys[1] or any(key not in selected for key in keys):
            raise AnalysisContractError("comparison requires distinct observed baseline and candidate")
        baseline, candidate = (selected[key] for key in keys)
        conditions = ("measurement_source", "unity_version", "platform", "graphics_api", "capture_mode", "build_type", "scene_or_scope", "measurement_window")
        if any(baseline["metadata"][name] != candidate["metadata"][name] for name in conditions) or any(item["metadata"]["validity"] != "valid" for item in (baseline, candidate)):
            raise AnalysisContractError("comparison requires valid captures under the same conditions")
        before, after, deltas = _metrics(baseline["metrics"]), _metrics(candidate["metrics"]), _metrics(comparison["deltas"])
        if set(before) != set(after) or set(deltas) != set(before) or not deltas:
            raise AnalysisContractError("comparison metrics do not match")
        for name, delta in deltas.items():
            if any(before[name][field] != after[name][field] or delta[field] != after[name][field] for field in ("unit", "category")) or not math.isclose(delta["value"], after[name]["value"] - before[name]["value"], rel_tol=1e-9, abs_tol=1e-12):
                raise AnalysisContractError("comparison delta is not supported by observations")
    return {"status": "runtime_contract_verified", "evidence_type": "performance_analysis", "evidence_level": "runtime_reasoning", "runtime_evaluation": "RUNTIME_OBSERVED"}
