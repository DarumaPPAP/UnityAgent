"""観測済みContent Factから変更候補を計算するread-only Pilot。"""
from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any


def _path(value: dict[str, Any]) -> str:
    path = value.get("asset_path")
    if not isinstance(path, str) or not path.startswith("Assets/") or ".." in path.replace("\\", "/").split("/"):
        raise ValueError("Content observation needs a bounded Assets path")
    return path


def _result(domain: str, observation: dict[str, Any], status: str) -> dict[str, Any]:
    return {"domain": domain, "status": status, "asset_path": _path(observation), "observed": deepcopy(observation), "observation_source_ref": observation.get("evidence_ref") or "input_unverified", "proposed_changes": [], "approval_required": False, "applied": False, "evidence_level": "input_observation_only"}


def _texture_plan(result: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    proposed = result["proposed_format"]
    if proposed is None:
        return result
    current = observation.get("current_format")
    if not isinstance(current, str) or not current:
        result["status"] = "candidate_only"
        return result
    if current != proposed:
        result.update(status="change_plan", proposed_changes=[{"field": "format", "before": current, "after": proposed}], approval_required=True)
    return result


def analyze_texture(observation: dict[str, Any], *, project_decision: dict[str, Any]) -> dict[str, Any]:
    result = _result("texture", observation, "observed")
    result.update(classification="unobserved", proposed_format=None, proposed_max_size=None, confidence=None)
    usage = observation.get("usage")
    if usage not in {"normal", "color", "mask", "height"}:
        raise ValueError("texture usage must be observed")
    if type(observation.get("width")) is not int or type(observation.get("height")) is not int or observation["width"] < 1 or observation["height"] < 1 or type(observation.get("has_alpha")) is not bool:
        raise ValueError("texture dimensions and alpha must be observed")
    if usage == "normal":
        samples = observation.get("sampled_normals")
        minimum = project_decision.get("normal_flat_min_samples")
        distance = project_decision.get("normal_flat_distance")
        threshold = project_decision.get("normal_flat_confidence")
        if not isinstance(samples, list) or type(minimum) is not int or minimum < 1 or len(samples) < minimum or not all(type(value) in (int, float) and math.isfinite(value) for value in (distance, threshold)) or not (0 < distance <= 1 and 0 < threshold <= 1):
            return result
        if any(not isinstance(sample, list) or len(sample) != 3 or any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1 for value in sample) for sample in samples):
            raise ValueError("normal samples must be observed normalized RGB triples")
        count = sum(math.dist(sample, [0.5, 0.5, 1.0]) <= distance for sample in samples)
        confidence = count / len(samples)
        low = confidence >= threshold
        result["classification"] = "low_normal_candidate" if low else "high_normal_candidate"
        result["confidence"] = confidence
        result["classification_criteria"] = {"flat_distance": distance, "minimum_samples": minimum, "flat_fraction_threshold": threshold, "observed_samples": len(samples)}
        format_key = "low_normal_format" if low else "high_normal_format"
        proposed = project_decision.get(format_key)
        if proposed in {"BC1", "BC5"}:
            result["proposed_format"] = proposed
        return _texture_plan(result, observation)
    result["classification"] = usage
    formats = project_decision.get("color_formats") if usage == "color" else project_decision.get("scalar_formats")
    if isinstance(formats, dict):
        proposed = formats.get("with_alpha" if observation["has_alpha"] else "without_alpha")
        if proposed in {"BC1", "BC3", "BC4"}:
            result["proposed_format"] = proposed
    return _texture_plan(result, observation)


def analyze_audio(observation: dict[str, Any], *, project_decision: dict[str, Any] | None) -> dict[str, Any]:
    result = _result("audio", observation, "observed")
    fields = ("load_type", "compression_format", "quality", "preload", "load_in_background", "platform_overrides", "original_size_bytes")
    if any(field not in observation for field in fields) or type(observation["original_size_bytes"]) is not int or observation["original_size_bytes"] < 0 or type(observation["quality"]) not in (int, float) or not math.isfinite(observation["quality"]) or not isinstance(observation["platform_overrides"], dict):
        raise ValueError("audio importer facts are incomplete")
    if project_decision is None:
        return result
    allowed = {"load_type", "compression_format", "quality", "preload", "load_in_background"}
    if not isinstance(project_decision, dict) or set(project_decision) - allowed:
        raise ValueError("audio decision contains unsupported importer fields")
    changes = [{"field": field, "before": observation[field], "after": project_decision[field]} for field in sorted(project_decision) if observation[field] != project_decision[field]]
    if changes:
        result.update(status="change_plan", proposed_changes=changes, approval_required=True)
    return result


def analyze_addressables(observation: dict[str, Any], *, proposed_group: str | None = None, proposed_address: str | None = None) -> dict[str, Any]:
    result = _result("addressables", observation, "observed")
    if observation.get("package_installed") is not True:
        result["status"] = "unsupported" if observation.get("package_installed") is False else "unavailable"
        return result
    if observation.get("settings_present") is not True:
        result["status"] = "unavailable"
        return result
    if not isinstance(observation.get("groups"), list) or any(not isinstance(group, str) for group in observation["groups"]):
        raise ValueError("Addressables groups must be observed")
    if proposed_group is None and proposed_address is None:
        return result
    if proposed_group not in observation["groups"] or not isinstance(proposed_address, str) or not proposed_address:
        result["status"] = "unavailable"
        return result
    revision = observation.get("revision")
    if not isinstance(revision, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", revision) is None:
        result["status"] = "unavailable"
        return result
    result["expected_revision"] = revision
    result["proposed_changes"] = [{"field": "group", "before": observation.get("current_group"), "after": proposed_group}, {"field": "address", "before": observation.get("current_address"), "after": proposed_address}]
    result["status"] = "change_plan"
    result["approval_required"] = True
    return result
