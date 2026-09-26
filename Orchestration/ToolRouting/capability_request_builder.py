"""Build provider-unresolved CapabilityRequest values from semantic route templates."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROUTING_PATH = Path("Orchestration/ToolRouting/capability-routing.yaml")
MUTATION_OPERATION_KINDS = {
    "source_mutation",
    "editor_mutation",
    "save",
    "bake",
    "player_mutate",
    "arbitrary_code",
}


def conditions_for_intent(intent: dict[str, Any], fingerprint: dict[str, str]) -> set[str]:
    """Translate explicit outcomes into existing routing conditions, failing closed on contradictions."""
    kind = intent.get("kind")
    if (kind == "project_inspection" and fingerprint["artifact"] == "project"
            and fingerprint["scope"] == "read_only" and fingerprint["mutation_target"] == "none"):
        return {"project_fact_needed"}
    if (kind == "visual_capture" and fingerprint["artifact"] == "visual"
            and fingerprint["scope"] == "project_asset" and fingerprint["mutation_target"] == "none"):
        return {"visual_evidence_needed"}
    if kind == "rendering_diagnosis" and fingerprint["artifact"] == "rendering" and fingerprint["failure_mode"] == "rendering_unknown":
        return {"project_fact_needed"}
    if kind == "performance_analysis" and fingerprint["artifact"] == "performance" and fingerprint["failure_mode"] == "performance":
        return {"project_fact_needed"}
    raise ValueError(f"no verified Capability conditions for intent kind: {kind}")


def task_contract_projection(route_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    catalog = yaml.safe_load((root / "Context/Selection/context-catalog.yaml").read_text(encoding="utf-8"))
    selected = (catalog.get("routes") or {}).get(route_id)
    if not isinstance(selected, dict):
        raise ValueError(f"no Task Contract for route: {route_id}")
    ref = str(selected["task_contract"])
    contract = yaml.safe_load((root / ref).read_text(encoding="utf-8"))
    if contract.get("id") != route_id:
        raise ValueError(f"Task Contract does not match selected route: {route_id}")
    projection = {"task_contract_ref": ref, "id": route_id, "risk_level": contract["risk_level"],
                  "required_quality_gates": list(contract.get("required_quality_gates") or [])}
    return projection


def _load(root: Path) -> dict[str, Any]:
    value = yaml.safe_load((root / ROUTING_PATH).read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError("capability routing must be a mapping")
    return value


def build_capability_requests(
    *,
    route_id: str,
    project_root: str,
    active_conditions: set[str] | None = None,
    mutation_scope: dict[str, Any] | None = None,
    approval_ref: str | None = None,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    if not project_root.strip():
        raise ValueError("project_root is required")

    routing = _load(root)
    routes = routing.get("routes") or {}
    route = routes.get(route_id)
    if not isinstance(route, dict):
        raise ValueError(f"unknown capability route: {route_id}")

    declared_conditions = set(routing.get("conditions") or [])
    conditions = set(active_conditions or set())
    unknown_conditions = conditions.difference(declared_conditions)
    if unknown_conditions:
        raise ValueError(f"unknown capability condition(s): {sorted(unknown_conditions)}")

    requests: list[dict[str, Any]] = []
    for template in route.get("capabilities") or []:
        when = str(template.get("when") or "")
        if when != "always" and when not in conditions:
            continue

        operation_kind = str(template.get("operation_kind") or "")
        request_scope: dict[str, Any] | None = None
        if operation_kind in MUTATION_OPERATION_KINDS:
            if not isinstance(mutation_scope, dict) or not mutation_scope.get("allowed_paths"):
                raise ValueError(
                    f"mutation_scope is required for {template.get('capability')} ({operation_kind})"
                )
            request_scope = mutation_scope

        request = {
                "schema_version": "1.0",
                "capability": str(template["capability"]),
                "project_root": project_root,
                "operation_kind": operation_kind,
                "required_evidence": [str(item) for item in template.get("required_evidence") or []],
                "mutation_scope": request_scope,
                "approval_ref": approval_ref,
                "preferred_surface": template.get("preferred_surface"),
            }
        qualifiers = template.get("qualifiers")
        if qualifiers is not None:
            if not isinstance(qualifiers, dict):
                raise ValueError(f"qualifiers must be a mapping for {template.get('capability')}")
            request["qualifiers"] = dict(qualifiers)
        requests.append(request)
    return requests


def build_candidate_capability_requests(route_id: str, project_root: str, *, active_conditions: set[str] | None = None, root: Path = ROOT) -> list[dict[str, Any]]:
    """Build semantic candidate requests from the route, without Production dispatch authority."""
    route = (_load(root).get("routes") or {}).get(route_id)
    if not isinstance(route, dict):
        raise ValueError(f"unknown capability route: {route_id}")
    conditions = set(active_conditions or set()) | {"always"}
    return [{"schema_version": "1.0", "capability": str(item["capability"]), "project_root": project_root,
             "operation_kind": str(item["operation_kind"]), "required_evidence": list(item["required_evidence"]),
             "mutation_scope": None, "approval_ref": None, "preferred_surface": item.get("preferred_surface")}
            for item in route.get("candidate_capabilities") or [] if item.get("when") in conditions]
