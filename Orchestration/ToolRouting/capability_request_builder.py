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

        requests.append(
            {
                "schema_version": "1.0",
                "capability": str(template["capability"]),
                "project_root": project_root,
                "operation_kind": operation_kind,
                "required_evidence": [str(item) for item in template.get("required_evidence") or []],
                "mutation_scope": request_scope,
                "approval_ref": approval_ref,
                "preferred_surface": template.get("preferred_surface"),
            }
        )
    return requests
