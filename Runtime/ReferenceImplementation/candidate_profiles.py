"""Providerを選ばないRegistered Specialist候補のProfileと選出契約。"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
PROFILE_ID = re.compile(r"^[a-z][a-z0-9_]*_subagent$")
CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
CONTEXT_KEY = re.compile(r"^(?:project_fact|project_decision|platform_fact|platform_decision|task_fact):[a-z][a-z0-9_]*$")
PROFILE_FIELDS = {"profile_id", "display_name", "audience", "goal_type", "capabilities", "required_evidence", "execution_mode", "provider_resolution", "runtime_evaluation", "activation", "compatibility", "capability_context"}


class CandidateProfileError(ValueError):
    pass


def _texts(value: Any, name: str, pattern: re.Pattern[str] | None = None) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value) or len(set(value)) != len(value):
        raise CandidateProfileError(f"{name} requires unique non-empty strings")
    if pattern and any(pattern.fullmatch(item) is None for item in value):
        raise CandidateProfileError(f"{name} has an invalid item")
    return value


def validate_candidate_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict) or set(profile) != PROFILE_FIELDS:
        raise CandidateProfileError("Candidate Profile fields are not exact")
    if not isinstance(profile["profile_id"], str) or PROFILE_ID.fullmatch(profile["profile_id"]) is None:
        raise CandidateProfileError("invalid candidate profile_id")
    for field in ("display_name", "audience", "goal_type"):
        if not isinstance(profile[field], str) or not profile[field]:
            raise CandidateProfileError(f"invalid {field}")
    capabilities = _texts(profile["capabilities"], "capabilities", CAPABILITY_ID)
    if profile["goal_type"] not in capabilities or profile["audience"] != profile["profile_id"]:
        raise CandidateProfileError("goal_type or audience does not match candidate identity")
    _texts(profile["required_evidence"], "required_evidence")
    if profile["execution_mode"] != "read_only_analysis" or profile["provider_resolution"] != "runtime_tool_broker" or profile["runtime_evaluation"] != "NOT_EVALUATED_RUNTIME":
        raise CandidateProfileError("unsupported Candidate execution contract")
    activation = profile["activation"]
    if not isinstance(activation, dict) or set(activation) != {"required_environment"}:
        raise CandidateProfileError("activation fields are not exact")
    _texts(activation["required_environment"], "activation.required_environment")
    compatibility = profile["compatibility"]
    if not isinstance(compatibility, dict) or set(compatibility) != {"unity_version_prefixes", "context_values"}:
        raise CandidateProfileError("compatibility fields are not exact")
    _texts(compatibility["unity_version_prefixes"], "compatibility.unity_version_prefixes")
    if not isinstance(compatibility["context_values"], dict):
        raise CandidateProfileError("compatibility.context_values must be a mapping")
    for key, allowed in compatibility["context_values"].items():
        if not isinstance(key, str) or CONTEXT_KEY.fullmatch(key) is None:
            raise CandidateProfileError("invalid compatibility Context key")
        _texts(allowed, f"compatibility.context_values.{key}")
    requirements = profile["capability_context"]
    if not isinstance(requirements, dict) or set(requirements) != set(capabilities):
        raise CandidateProfileError("each capability requires a Context contract")
    for capability, requirement in requirements.items():
        if not isinstance(requirement, dict) or set(requirement) != {"all_of", "any_of", "receipt_required"} or requirement["receipt_required"] is not True:
            raise CandidateProfileError(f"invalid Context contract: {capability}")
        _texts(requirement["all_of"], f"{capability}.all_of", CONTEXT_KEY)
        _texts(requirement["any_of"], f"{capability}.any_of", CONTEXT_KEY)
        if any(key not in requirement["all_of"] for key in compatibility["context_values"]):
            raise CandidateProfileError(f"{capability} must require each compatibility Context key")
    return profile


def load_candidate_profile(profile_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    catalog = yaml.safe_load((root / "Runtime/ReferenceImplementation/candidate-specialists.yaml").read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or set(catalog) != {"schema_version", "kind", "profiles"} or catalog["schema_version"] != "1.0" or catalog["kind"] != "candidate_specialist_catalog" or not isinstance(catalog["profiles"], dict):
        raise CandidateProfileError("Candidate Catalog is invalid")
    reference = catalog["profiles"].get(profile_id)
    if reference is None:
        raise CandidateProfileError(f"unknown candidate profile: {profile_id}")
    if not isinstance(reference, str) or re.fullmatch(r"Runtime/ReferenceImplementation/[a-z][a-z0-9_-]*\.yaml", reference) is None:
        raise CandidateProfileError("Candidate Profile reference is invalid")
    profile = validate_candidate_profile(yaml.safe_load((root / reference).read_text(encoding="utf-8")))
    if profile["profile_id"] != profile_id:
        raise CandidateProfileError("Candidate Catalog identity mismatch")
    return profile


def _fact(snapshot: Mapping[str, Any], dotted_path: str) -> Any:
    value: Any = snapshot
    for segment in dotted_path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(segment)
    return value


def _context_values(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items or []:
        if not isinstance(item, dict) or not isinstance(item.get("category"), str) or not isinstance(item.get("key"), str):
            continue
        freshness = item.get("freshness")
        if not isinstance(freshness, Mapping) or freshness.get("status") != "current" or item.get("value") in (None, "unknown"):
            continue
        result[f"{item['category']}:{item['key']}"] = item["value"]
    return result


def resolve_candidate(profile: dict[str, Any], capability: str, snapshot: Mapping[str, Any], *, pilot_enabled: bool, specialist_capability_mutates: bool = False, context_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    profile = validate_candidate_profile(profile)
    common = {"profile_id": None, "capability": capability}
    if capability not in profile["capabilities"] or specialist_capability_mutates:
        return {**common, "status": "unsupported", "reason_code": "capability_unsupported"}
    if not pilot_enabled:
        return {**common, "status": "unavailable", "reason_code": "pilot_disabled"}
    version = _fact(snapshot, "project.unity_version")
    if not isinstance(version, str) or not version:
        return {**common, "status": "unavailable", "reason_code": "unity_version_unobserved"}
    if not any(version.startswith(prefix) for prefix in profile["compatibility"]["unity_version_prefixes"]):
        return {**common, "status": "unsupported", "reason_code": "unity_version_unsupported"}
    for path in profile["activation"]["required_environment"]:
        if _fact(snapshot, path) is not True:
            return {**common, "status": "unavailable", "reason_code": "activation_fact_unavailable", "required_observations": [path]}
    values = _context_values(context_items)
    requirement = profile["capability_context"][capability]
    missing = [key for key in requirement["all_of"] if key not in values]
    if not any(key in values for key in requirement["any_of"]):
        missing.extend(requirement["any_of"])
    if missing:
        return {**common, "status": "unavailable", "reason_code": "required_context_missing", "required_observations": sorted(set(missing))}
    for key, allowed in profile["compatibility"]["context_values"].items():
        if values[key] not in allowed:
            return {**common, "status": "unsupported", "reason_code": "context_value_unsupported", "unsupported_context_key": key}
    return {"status": "selected", "profile_id": profile["profile_id"], "capability": capability, "required_evidence": list(profile["required_evidence"]), "receipt_required": requirement["receipt_required"]}
