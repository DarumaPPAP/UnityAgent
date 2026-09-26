"""Providerless World Plan候補の静的Artifactを検証する。Unity実行の証明ではない。"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class WorldPlanContractError(ValueError):
    pass


class WorldPlanContextError(WorldPlanContractError):
    pass


RESULT_FIELDS = frozenset({"status", "profile_id", "capability", "execution_mode", "provider_resolution", "source_context_id", "source_context_fingerprint", "world_plan", "evidence_level", "known_limitations", "runtime_evaluation"})
PLAN_FIELDS = frozenset({"world_goal", "scene_scope", "environment_type", "visual_intent", "zones", "camera_requirements", "lighting_requirements", "content_requirements", "technical_constraints", "performance_constraints", "platform_constraints", "prohibited_changes", "acceptance_criteria", "work_packages", "dependencies", "required_evidence", "open_decisions", "human_review_required", "direct_unity_mutation", "automatic_visual_acceptance"})
PACKAGE_FIELDS = frozenset({"id", "goal", "scope", "domain_hint", "depends_on", "constraints", "acceptance_criteria", "required_evidence"})
DOMAIN_HINTS = frozenset({"visual", "graphics", "performance", "content", "generic_unity"})
FORBIDDEN_GOAL_PREFIXES = ("set material ", "move object ", "execute shader patch", "save scene", "bake lighting")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _texts(value: Any, *, required: bool = False) -> bool:
    return isinstance(value, list) and (bool(value) or not required) and all(_text(item) for item in value)


def _context_items(specialist: Mapping[str, Any]) -> dict[str, Any]:
    return {item["key"]: item["value"] for item in specialist.get("items", []) if isinstance(item, Mapping) and item.get("type") == "task_fact" and _text(item.get("key"))}


def _validate_dependencies(packages: list[Mapping[str, Any]], edges: list[Mapping[str, Any]]) -> None:
    ids = [item["id"] for item in packages]
    if len(set(ids)) != len(ids):
        raise WorldPlanContractError("work package IDs must be unique")
    expected = {(dependency, item["id"]) for item in packages for dependency in item["depends_on"]}
    if any(dependency not in ids or dependency == item["id"] for item in packages for dependency in item["depends_on"]):
        raise WorldPlanContractError("work package dependency is invalid")
    if any(not isinstance(edge, Mapping) or set(edge) != {"before", "after"} or not _text(edge["before"]) or not _text(edge["after"]) for edge in edges):
        raise WorldPlanContractError("dependency edge is invalid")
    actual = {(edge["before"], edge["after"]) for edge in edges}
    if actual != expected or len(edges) != len(actual):
        raise WorldPlanContractError("dependency graph differs from work packages")
    pending = set(ids)
    while pending:
        ready = {item for item in pending if not any(after == item and before in pending for before, after in actual)}
        if not ready:
            raise WorldPlanContractError("work package dependency cycle")
        pending.difference_update(ready)


def verify_world_plan(manifest: Mapping[str, Any], result: Mapping[str, Any], *, runtime_observed: bool = False) -> dict[str, Any]:
    """Generated Contextへの参照とWorld Planの安全境界を照合する。"""
    view = manifest.get("materialized_context")
    if not isinstance(view, Mapping) or not isinstance(view.get("specialist_context"), Mapping):
        raise WorldPlanContractError("World Specialist Context is missing")
    specialist = view["specialist_context"]
    if any(specialist.get(key) != value for key, value in {"profile_id": "world_creator_subagent", "capability": "world.plan", "execution_mode": "planning_only", "provider_resolution": "not_required"}.items()):
        raise WorldPlanContractError("World Specialist Context contract is invalid")
    expected = (view.get("context_id"), (view.get("context_fingerprint") or {}).get("value"))
    if not all(_text(value) for value in expected):
        raise WorldPlanContractError("generated Context identity is invalid")
    if not isinstance(result, Mapping) or set(result) != RESULT_FIELDS:
        raise WorldPlanContractError("World Plan Result fields are not exact")
    if (result["source_context_id"], result["source_context_fingerprint"]) != expected:
        raise WorldPlanContextError("source Context identity or fingerprint does not match generated Context")
    level = "runtime_reasoning" if runtime_observed else "static"
    evaluation = "RUNTIME_OBSERVED" if runtime_observed else "NOT_EVALUATED_RUNTIME"
    if any(result[key] != value for key, value in {"status": "completed", "profile_id": "world_creator_subagent", "capability": "world.plan", "execution_mode": "planning_only", "provider_resolution": "not_required", "evidence_level": level, "runtime_evaluation": evaluation}.items()) or not _texts(result["known_limitations"]):
        raise WorldPlanContractError("World Plan Result claims invalid execution or evidence")
    plan = result["world_plan"]
    if not isinstance(plan, Mapping) or set(plan) != PLAN_FIELDS:
        raise WorldPlanContractError("World Plan fields are not exact")
    if plan["human_review_required"] is not True or plan["direct_unity_mutation"] is not False or plan["automatic_visual_acceptance"] is not False:
        raise WorldPlanContractError("World Plan safety values are invalid")
    if not _text(plan["world_goal"]) or not _text(plan["scene_scope"]) or any(plan[key] is not None and not _text(plan[key]) for key in ("environment_type", "visual_intent")):
        raise WorldPlanContractError("World Goal, Scope, or optional decision is invalid")
    for key in ("zones", "camera_requirements", "lighting_requirements", "content_requirements", "technical_constraints", "performance_constraints", "platform_constraints", "prohibited_changes", "acceptance_criteria", "required_evidence", "open_decisions"):
        if not _texts(plan[key], required=key in {"acceptance_criteria", "required_evidence"}):
            raise WorldPlanContractError(f"World Plan {key} must be a text list")
    if "world_plan" not in plan["required_evidence"]:
        raise WorldPlanContractError("world_plan static evidence is required")
    facts = _context_items(specialist)
    if plan["world_goal"] != facts.get("world_goal") or plan["scene_scope"] != facts.get("requested_scope"):
        raise WorldPlanContractError("World Plan changed the requested goal or scope")
    for fact_key, plan_key in (("environment_type", "environment_type"), ("desired_mood", "visual_intent")):
        if fact_key in facts and plan[plan_key] != facts[fact_key]:
            raise WorldPlanContractError(f"World Plan changed supplied {fact_key}")
    for fact_key, plan_key in (("prohibited_changes", "prohibited_changes"), ("acceptance_criteria", "acceptance_criteria"), ("target_platforms", "platform_constraints")):
        if fact_key in facts and not _texts(facts[fact_key]):
            raise WorldPlanContractError(f"supplied {fact_key} is invalid")
        if fact_key in facts and not set(facts[fact_key]).issubset(set(plan[plan_key])):
            raise WorldPlanContractError(f"World Plan dropped supplied {fact_key}")
    if ("environment_type" not in facts and plan["environment_type"] is not None) or ("desired_mood" not in facts and plan["visual_intent"] is not None):
        raise WorldPlanContractError("World Plan invented an unobserved design decision")
    if "environment_type" not in facts and not any("environment_type" in item for item in plan["open_decisions"]):
        raise WorldPlanContractError("unknown environment_type must remain an open decision")
    if "desired_mood" not in facts and not any("desired_mood" in item for item in plan["open_decisions"]):
        raise WorldPlanContractError("unknown desired_mood must remain an open decision")
    observed_targets = [item["value"] for item in specialist.get("items", []) if isinstance(item, Mapping) and item.get("type") == "platform_fact" and item.get("key") == "requested_target"]
    if any(target not in plan["platform_constraints"] for target in observed_targets):
        raise WorldPlanContractError("World Plan dropped observed target platform")
    if "target_platforms" in facts and observed_targets and any(target not in facts["target_platforms"] for target in observed_targets) and not any("target_platform_conflict" in item for item in plan["open_decisions"]):
        raise WorldPlanContractError("conflicting target platforms require an open decision")
    platform_known = "target_platforms" in facts or bool(observed_targets)
    if not platform_known and (plan["platform_constraints"] or not any("target_platform" in item for item in plan["open_decisions"])):
        raise WorldPlanContractError("unknown target platform must remain an open decision")
    packages = plan["work_packages"]
    if not isinstance(packages, list) or not packages:
        raise WorldPlanContractError("World Plan requires work packages")
    for package in packages:
        if not isinstance(package, Mapping) or set(package) != PACKAGE_FIELDS or not all(_text(package[key]) for key in ("id", "goal", "scope")) or not isinstance(package["domain_hint"], str) or package["domain_hint"] not in DOMAIN_HINTS or not all(_texts(package[key], required=key in {"acceptance_criteria", "required_evidence"}) for key in ("depends_on", "constraints", "acceptance_criteria", "required_evidence")):
            raise WorldPlanContractError("work package shape is invalid")
        if any(command in package["goal"].strip().lower() for command in FORBIDDEN_GOAL_PREFIXES):
            raise WorldPlanContractError("work package contains a direct mutation command")
    if not isinstance(plan["dependencies"], list):
        raise WorldPlanContractError("dependencies must be a list")
    _validate_dependencies(packages, plan["dependencies"])
    return {"status": "runtime_contract_verified" if runtime_observed else "fixture_contract_verified", "evidence_type": "world_plan", "evidence_level": level, "runtime_evaluation": evaluation}
