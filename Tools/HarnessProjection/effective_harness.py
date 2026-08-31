"""Build and validate the read-only Effective Harness projection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml

REQUEST_BOUND = "request"
CONTEXT_CATALOG = "Context/Selection/context-catalog.yaml"
RUNTIME_PROFILES = "Runtime/Profiles/runtime-profiles.yaml"
RISK_LEVELS = "Policy/Risk/risk-levels.yaml"
QUALITY_GATES = "Policy/Evidence/quality-gates.yaml"
MUTATION_CHANNELS = "Runtime/Guardrails/mutation-channels.yaml"
MCP_ACTIVATION = "Runtime/Permissions/mcp-activation.yaml"

APPROVAL_POLICIES = {
    "not_required",
    "conditional",
    "before_destructive_or_contract_change",
    "required_for_project_asset_or_settings_change",
    "always_required",
}
PROJECT_ASSET_OR_SETTINGS_CHANNELS = {
    "scene",
    "prefab",
    "material",
    "project_settings",
    "render_pipeline_asset",
}


def read_yaml(root: Path, relative: str) -> dict[str, Any]:
    return yaml.safe_load((root / relative).read_text(encoding="utf-8")) or {}


def route_for_contract(root: Path, contract_path: str) -> tuple[str, dict[str, Any]]:
    catalog = read_yaml(root, CONTEXT_CATALOG)
    for route_id, route in (catalog.get("routes", {}) or {}).items():
        if route.get("task_contract") == contract_path:
            return str(route_id), route
    raise ValueError(f"No route binds task contract: {contract_path}")


def validate_task_contract_channels(
    contract: dict[str, Any],
    known_channels: Iterable[str],
) -> list[str]:
    errors: list[str] = []
    known = set(known_channels)
    allowed_mutations = list(contract.get("allowed_mutations", []) or [])
    declared_channels = list(contract.get("mutation_channels", []) or [])
    binding = contract.get("mutation_channel_binding")

    if declared_channels and binding:
        errors.append("Use mutation_channels or mutation_channel_binding, not both")
    if allowed_mutations and not declared_channels and binding != REQUEST_BOUND:
        errors.append(
            "Contracts with allowed mutations must declare mutation_channels "
            "or mutation_channel_binding: request"
        )
    unknown = sorted(set(declared_channels) - known)
    if unknown:
        errors.append(f"Unknown mutation channels: {unknown}")
    if binding not in {None, REQUEST_BOUND}:
        errors.append(f"Unknown mutation_channel_binding: {binding}")

    return errors


def resolve_mutation_channels(
    contract: dict[str, Any],
    request: dict[str, Any],
    known_channels: Iterable[str],
) -> list[str]:
    known = set(known_channels)
    errors = validate_task_contract_channels(contract, known)
    if errors:
        raise ValueError("; ".join(errors))

    if contract.get("mutation_channel_binding") == REQUEST_BOUND:
        channels = list(request.get("mutation_channels", []) or [])
    else:
        channels = list(contract.get("mutation_channels", []) or [])

    unknown = sorted(set(channels) - known)
    if unknown:
        raise ValueError(f"Unknown mutation channels: {unknown}")

    return sorted(set(channels))


def resolve_human_approval(
    approval_policy: str | None,
    mutation_channels: Iterable[str],
    request: dict[str, Any],
) -> dict[str, Any]:
    policy = approval_policy or "not_required"
    if policy not in APPROVAL_POLICIES:
        raise ValueError(f"Unknown human approval policy: {policy}")

    channels = set(mutation_channels)
    if policy == "not_required":
        required = False
        reason = "policy_not_required"
    elif policy == "conditional":
        required = bool(request.get("requires_human_approval", False))
        reason = "request_condition" if required else "condition_not_triggered"
    elif policy == "before_destructive_or_contract_change":
        destructive = bool(request.get("destructive_change", False))
        contract_change = bool(request.get("contract_change", False))
        required = destructive or contract_change
        reason = "destructive_or_contract_change" if required else "condition_not_triggered"
    elif policy == "required_for_project_asset_or_settings_change":
        explicit_project_change = bool(request.get("project_asset_or_settings_change", False))
        channel_project_change = bool(channels & PROJECT_ASSET_OR_SETTINGS_CHANNELS)
        required = explicit_project_change or channel_project_change
        reason = "project_asset_or_settings_change" if required else "condition_not_triggered"
    else:
        required = True
        reason = "always_required"

    granted = bool(request.get("human_approval_granted", False))
    return {
        "policy": policy,
        "required": required,
        "granted": granted,
        "satisfied": not required or granted,
        "reason": reason,
    }


def build_permission_projection(
    *,
    risk_level: str,
    approval_policy: str | None,
    mutation_channels: Iterable[str],
    allowed_mutations: Iterable[str],
    direct_mutation_authorized: bool,
    request: dict[str, Any],
) -> dict[str, Any]:
    allowed = list(allowed_mutations)
    unresolved = list(request.get("unresolved_bindings", []) or [])
    approval = resolve_human_approval(approval_policy, mutation_channels, request)

    if risk_level == "R0":
        mutate = "blocked"
        effective_allowed: list[str] = []
    elif unresolved or not direct_mutation_authorized or not approval["satisfied"]:
        mutate = "approval-dependent"
        effective_allowed = []
    else:
        effective_allowed = allowed
        mutate = "allowed" if effective_allowed else "approval-dependent"

    human_gates = []
    if approval["required"]:
        human_gates.append(
            {
                "id": "human_approval",
                "status": "passed" if approval["granted"] else "required",
                "reason": approval["reason"],
            }
        )

    return {
        "permission": {"read": "allowed", "plan": "allowed", "mutate": mutate},
        "allowed_mutations": effective_allowed,
        "human_approval": approval,
        "human_gates": human_gates,
    }


def build_effective_harness(
    root: Path,
    contract_path: str,
    execution_profile: str | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = request or {}
    contract = read_yaml(root, contract_path)
    route_id, _ = route_for_contract(root, contract_path)
    profiles = read_yaml(root, RUNTIME_PROFILES).get("profiles", {})
    profile_id = execution_profile or contract.get("default_execution_profile")
    if profile_id not in profiles:
        raise ValueError(f"Unknown execution profile: {profile_id}")

    risk_id = str(contract.get("risk_level", "R0"))
    risks = read_yaml(root, RISK_LEVELS).get("levels", {})
    if risk_id not in risks:
        raise ValueError(f"Unknown risk level: {risk_id}")

    allowed = list(contract.get("allowed_mutations", []) or [])
    prohibited = list(contract.get("prohibited_mutations", []) or [])
    explicit_approvals = set(request.get("explicit_approvals", []) or [])
    candidate_allowed = [item for item in allowed if item in explicit_approvals or not explicit_approvals]

    quality_catalog = read_yaml(root, QUALITY_GATES).get("gates", {})
    channel_catalog = read_yaml(root, MUTATION_CHANNELS).get("channels", {})
    mutation_channels = resolve_mutation_channels(contract, request, channel_catalog)

    direct_mutation_authorized = profile_id == "personal_full_control" and risk_id != "R0"
    if contract.get("mutation_channel_binding") == REQUEST_BOUND and not mutation_channels:
        direct_mutation_authorized = False

    permission_projection = build_permission_projection(
        risk_level=risk_id,
        approval_policy=risks[risk_id].get("human_approval"),
        mutation_channels=mutation_channels,
        allowed_mutations=candidate_allowed,
        direct_mutation_authorized=direct_mutation_authorized,
        request=request,
    )

    required_gates = list(contract.get("required_quality_gates", []) or [])
    conditional_gates = list(contract.get("conditional_quality_gates", []) or [])
    quality_gates = {
        "required": [
            {"id": gate, "status": "required" if gate in quality_catalog else "failed"}
            for gate in required_gates
        ],
        "conditional": [
            {"id": gate, "status": "required" if gate in quality_catalog else "failed"}
            for gate in conditional_gates
        ],
    }

    human_gates = list(permission_projection.get("human_gates", []) or [])
    if "visual" in contract.get("id", ""):
        human_gates.append({"id": "visual_review", "status": "required"})

    return {
        "task_contract": contract.get("id"),
        "execution_profile": profile_id,
        "route_id": route_id,
        "risk_level": risk_id,
        "permission": permission_projection["permission"],
        "allowed_mutations": permission_projection["allowed_mutations"],
        "prohibited_mutations": sorted(set(prohibited)),
        "mutation_channels": mutation_channels,
        "tool_groups": {
            "active": list(request.get("active_tool_groups", []) or []),
            "blocked": list(request.get("blocked_tool_groups", []) or []),
        },
        "quality_gates": quality_gates,
        "human_approval": permission_projection["human_approval"],
        "human_gates": human_gates,
        "stop_conditions": list(contract.get("stop_conditions", []) or []),
        "unresolved_bindings": list(request.get("unresolved_bindings", []) or []),
        "provenance": [
            {"source_path": contract_path, "reason": "harness_contract"},
            {"source_path": CONTEXT_CATALOG, "reason": "route_binding"},
            {"source_path": RUNTIME_PROFILES, "reason": "execution_profile"},
            {"source_path": RISK_LEVELS, "reason": "risk_level"},
            {"source_path": QUALITY_GATES, "reason": "quality_gate"},
            {"source_path": MUTATION_CHANNELS, "reason": "mutation_channel"},
            {"source_path": MCP_ACTIVATION, "reason": "tool_access"},
            {"source_path": "Tools/HarnessProjection/effective_harness.py", "reason": "harness_semantics"},
        ],
    }


def validate_effective_harness(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed = set(document.get("allowed_mutations", []) or [])
    prohibited = set(document.get("prohibited_mutations", []) or [])
    mutate_permission = document.get("permission", {}).get("mutate")

    if allowed & prohibited:
        errors.append("Mutation cannot be both allowed and prohibited")
    if document.get("risk_level") == "R0" and mutate_permission != "blocked":
        errors.append("R0 must block mutation")
    if document.get("unresolved_bindings") and document.get("allowed_mutations"):
        errors.append("Unresolved bindings must clear allowed mutations")
    if allowed and not document.get("mutation_channels"):
        errors.append("Allowed mutations require resolved mutation channels")

    approval = document.get("human_approval", {}) or {}
    if approval.get("required") and not approval.get("granted"):
        if mutate_permission == "allowed" or allowed:
            errors.append("Unsatisfied required human approval must block direct mutation")

    for group in ("required", "conditional"):
        for gate in document.get("quality_gates", {}).get(group, []) or []:
            if gate.get("status") == "failed":
                errors.append(f"Unknown quality gate: {gate.get('id')}")
            if gate.get("status") == "passed" and gate.get("id") in {"unavailable", "unknown"}:
                errors.append("Unavailable or unknown gate cannot be passed")
    return errors
