"""Deterministic semantic route selection. Context materialization consumes this decision; it does not make it."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml

REQUIRED_DIMENSIONS = ("intent", "artifact", "scope", "failure_mode", "architecture_state", "mutation_target", "evidence_state", "project_access")


def load_routes(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("authority") != "Orchestration":
        raise ValueError("task route catalog must be Orchestration authority")
    return data


def _matches(fingerprint: dict[str, str], rule: dict[str, list[str]]) -> bool:
    for dimension, allowed in rule.items():
        value = fingerprint.get(dimension)
        if value is None or value not in allowed:
            return False
    return True


def select_route(fingerprint: dict[str, str], catalog: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_DIMENSIONS if not str(fingerprint.get(key) or "").strip()]
    if missing:
        raise ValueError("fingerprint has unresolved required dimensions: " + ", ".join(missing))

    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for route_id, route in (catalog.get("routes") or {}).items():
        rule = route.get("fingerprint_match") or {}
        if _matches(fingerprint, rule):
            candidates.append((int(route.get("priority", 0)), len(rule), route_id, route))

    if not candidates:
        if fingerprint.get("scope") == "read_only" and fingerprint.get("mutation_target") == "none":
            return {"route_id": "generic-planning", "profile": _profile(fingerprint, None), "entry_action": "answer_only", "matched": False, "reason": "bounded read-only fallback"}
        return {"route_id": "generic-planning", "profile": _profile(fingerprint, None), "entry_action": "plan", "matched": False, "reason": "unmatched fingerprint fallback"}

    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    top = candidates[0]
    tied = [item for item in candidates if item[0] == top[0] and item[1] == top[1]]
    if len(tied) > 1:
        raise ValueError("ambiguous route fingerprint: " + ", ".join(item[2] for item in tied))
    route = top[3]
    return {"route_id": top[2], "profile": _profile(fingerprint, route.get("forced_profile")), "entry_action": route.get("entry_action", "plan"), "matched": True, "reason": "highest-specificity semantic route"}


def _profile(fingerprint: dict[str, str], forced: str | None) -> str:
    if forced:
        return forced
    access = fingerprint.get("project_access")
    if access == "authorized":
        return "personal_full_control"
    if access == "restricted" and fingerprint.get("scope") == "safe_import":
        return "team_safe_import"
    return "generic_planning"
