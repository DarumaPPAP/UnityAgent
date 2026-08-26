"""Build and validate the read-only Effective Harness projection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from unityagent_core.contracts import REQUEST_BOUND, resolve_mutation_channels
from unityagent_core.harness import build_permission_projection


def read_yaml(root: Path, relative: str) -> dict[str, Any]:
    return yaml.safe_load((root / relative).read_text(encoding="utf-8")) or {}


def route_for_contract(root: Path, contract_path: str) -> tuple[str, dict[str, Any]]:
    index = read_yaml(root, ".ai/context-index.yaml")
    for route_key, route in (index.get("routes", {}) or {}).items():
        if route.get("task_contract") == contract_path:
            return str(route.get("id", route_key)), route
    raise ValueError(f"No route binds task contract: {contract_path}")


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

    risk_id = str(contract.get("risk_level", "R0"))
    risks = read_yaml(root, ".ai/harness/risk-levels.yaml").get("levels", {})
    if risk_id not in risks:
        raise ValueError(f"Unknown risk level: {risk_id}")

    allowed = list(contract.get("allowed_mutations", []) or [])
    prohibited = list(contract.get("prohibited_mutations", []) or [])
    explicit_approvals = set(request.get("explicit_approvals", []) or [])
    candidate_allowed = [item for item in allowed if item in explicit_approvals or not explicit_approvals]

    quality_catalog = read_yaml(root, ".ai/harness/quality-gates.yaml").get("gates", {})
    channel_catalog = read_yaml(root, ".ai/harness/mutation-channels.yaml").get("channels", {})
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
        "human_approval": permission_projection.get("human_approval", {}),
        "human_gates": human_gates,
        "stop_conditions": list(contract.get("stop_conditions", []) or []),
        "unresolved_bindings": list(request.get("unresolved_bindings", []) or []),
        "provenance": [
            {"source_path": contract_path, "reason": "harness_contract"},
            {"source_path": ".ai/execution-profiles.yaml", "reason": "execution_profile"},
            {"source_path": ".ai/harness/risk-levels.yaml", "reason": "risk_level"},
            {"source_path": ".ai/harness/quality-gates.yaml", "reason": "quality_gate"},
            {"source_path": ".ai/harness/mutation-channels.yaml", "reason": "mutation_channel"},
            {"source_path": ".ai/harness/mcp-activation.yaml", "reason": "tool_access"},
            {"source_path": "DarumaPPAP/UnityAgent-Core", "reason": "harness_semantic_core"},
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
