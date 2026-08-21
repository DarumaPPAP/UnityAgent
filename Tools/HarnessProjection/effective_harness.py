"""Build and validate the read-only Effective Harness projection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def read_yaml(root: Path, relative: str) -> dict[str, Any]:
    return yaml.safe_load((root / relative).read_text(encoding="utf-8")) or {}


def route_for_contract(root: Path, contract_path: str) -> tuple[str, dict[str, Any]]:
    index = read_yaml(root, ".ai/context-index.yaml")
    for route_key, route in (index.get("routes", {}) or {}).items():
        if route.get("task_contract") == contract_path:
            return str(route.get("id", route_key)), route
    raise ValueError(f"No route binds task contract: {contract_path}")


def infer_channels(contract_id: str) -> list[str]:
    mapping = {
        "csharp": ["csharp"],
        "shader": ["shader"],
        "renderer": ["render_pipeline_asset"],
        "asset": ["scene", "prefab", "material", "project_settings"],
        "graphics": ["my_unity_mcp_tooling"],
        "portable": ["package"],
        "safe-import": ["package"],
    }
    channels: set[str] = set()
    for token, values in mapping.items():
        if token in contract_id:
            channels.update(values)
    return sorted(channels)


def build_effective_harness(
    root: Path,
    contract_path: str,
    execution_profile: str | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = request or {}
    contract = read_yaml(root, contract_path)
    route_id, route = route_for_contract(root, contract_path)
    profiles = read_yaml(root, ".ai/execution-profiles.yaml").get("profiles", {})
    profile_id = execution_profile or contract.get("default_execution_profile")
    if profile_id not in profiles:
        raise ValueError(f"Unknown execution profile: {profile_id}")
    profile = profiles[profile_id]
    risk_id = str(contract.get("risk_level", "R0"))
    risks = read_yaml(root, ".ai/harness/risk-levels.yaml").get("levels", {})
    if risk_id not in risks:
        raise ValueError(f"Unknown risk level: {risk_id}")

    allowed = list(contract.get("allowed_mutations", []) or [])
    prohibited = list(contract.get("prohibited_mutations", []) or [])
    unresolved = list(request.get("unresolved_bindings", []) or [])
    explicit_approvals = set(request.get("explicit_approvals", []) or [])
    direct_mutation_allowed = profile_id == "personal_full_control" and risk_id != "R0"
    if unresolved:
        direct_mutation_allowed = False
    if risk_id == "R0":
        effective_allowed: list[str] = []
        mutate_permission = "blocked"
    elif not direct_mutation_allowed:
        effective_allowed = []
        mutate_permission = "approval-dependent"
    else:
        effective_allowed = [item for item in allowed if item in explicit_approvals or not explicit_approvals]
        mutate_permission = "allowed" if effective_allowed else "approval-dependent"

    quality_catalog = read_yaml(root, ".ai/harness/quality-gates.yaml").get("gates", {})
    channel_catalog = read_yaml(root, ".ai/harness/mutation-channels.yaml").get("channels", {})
    mutation_channels = infer_channels(str(contract.get("id", "")))
    unknown_channels = sorted(set(mutation_channels) - set(channel_catalog))
    if unknown_channels:
        raise ValueError(f"Unknown mutation channels: {unknown_channels}")
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
    human_gates = []
    if risks[risk_id].get("human_approval") not in {"not_required", None}:
        human_gates.append({"id": "human_approval", "status": "required"})
    if "visual" in contract.get("id", ""):
        human_gates.append({"id": "visual_review", "status": "required"})

    return {
        "task_contract": contract.get("id"),
        "execution_profile": profile_id,
        "route_id": route_id,
        "risk_level": risk_id,
        "permission": {"read": "allowed", "plan": "allowed", "mutate": mutate_permission},
        "allowed_mutations": effective_allowed,
        "prohibited_mutations": sorted(set(prohibited)),
        "mutation_channels": mutation_channels,
        "tool_groups": {
            "active": list(request.get("active_tool_groups", []) or []),
            "blocked": list(request.get("blocked_tool_groups", []) or []),
        },
        "quality_gates": quality_gates,
        "human_gates": human_gates,
        "stop_conditions": list(contract.get("stop_conditions", []) or []),
        "unresolved_bindings": unresolved,
        "provenance": [
            {"source_path": contract_path, "reason": "harness_contract"},
            {"source_path": ".ai/execution-profiles.yaml", "reason": "execution_profile"},
            {"source_path": ".ai/harness/risk-levels.yaml", "reason": "risk_level"},
            {"source_path": ".ai/harness/quality-gates.yaml", "reason": "quality_gate"},
            {"source_path": ".ai/harness/mutation-channels.yaml", "reason": "mutation_channel"},
            {"source_path": ".ai/harness/mcp-activation.yaml", "reason": "tool_access"},
        ],
    }


def validate_effective_harness(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed = set(document.get("allowed_mutations", []) or [])
    prohibited = set(document.get("prohibited_mutations", []) or [])
    if allowed & prohibited:
        errors.append("Mutation cannot be both allowed and prohibited")
    if document.get("risk_level") == "R0" and document.get("permission", {}).get("mutate") != "blocked":
        errors.append("R0 must block mutation")
    if document.get("unresolved_bindings") and document.get("allowed_mutations"):
        errors.append("Unresolved bindings must clear allowed mutations")
    for group in ("required", "conditional"):
        for gate in document.get("quality_gates", {}).get(group, []) or []:
            if gate.get("status") == "failed":
                errors.append(f"Unknown quality gate: {gate.get('id')}")
            if gate.get("status") == "passed" and gate.get("id") in {"unavailable", "unknown"}:
                errors.append("Unavailable or unknown gate cannot be passed")
    return errors
