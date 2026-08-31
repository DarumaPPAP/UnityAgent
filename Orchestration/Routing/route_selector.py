"""Deterministic semantic route selection. Context materialization consumes this decision; it does not make it."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml

REQUIRED_DIMENSIONS = ("intent", "artifact", "scope", "failure_mode", "architecture_state", "mutation_target", "evidence_state", "project_access")
DESIGN_REVIEW_REQUIREMENTS = {"required", "conditional", "not_required"}


def load_routes(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("authority") != "Orchestration":
        raise ValueError("task route catalog must be Orchestration authority")
    for route_id, route in (data.get("routes") or {}).items():
        requirement = route.get("design_review", "not_required")
        if requirement not in DESIGN_REVIEW_REQUIREMENTS:
            raise ValueError(f"invalid design_review requirement for {route_id}: {requirement}")
    return data


def _matches(fingerprint: dict[str, str], rule: dict[str, list[str]]) -> bool:
    for dimension, allowed in rule.items():
        value = fingerprint.get(dimension)
        if value is None or value not in allowed:
            return False
    return True


def _decision(*, route_id: str, fingerprint: dict[str, str], route: dict[str, Any] | None, entry_action: str, matched: bool, reason: str) -> dict[str, Any]:
    return {
        "route_id": route_id,
        "profile": _profile(fingerprint, route.get("forced_profile") if route else None),
        "entry_action": entry_action,
        "design_review": (route or {}).get("design_review", "conditional" if route_id == "generic-planning" else "not_required"),
        "matched": matched,
        "reason": reason,
    }


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
            return _decision(route_id="generic-planning", fingerprint=fingerprint, route=None, entry_action="answer_only", matched=False, reason="bounded read-only fallback")
        return _decision(route_id="generic-planning", fingerprint=fingerprint, route=None, entry_action="plan", matched=False, reason="unmatched fingerprint fallback")

    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    top = candidates[0]
    tied = [item for item in candidates if item[0] == top[0] and item[1] == top[1]]
    if len(tied) > 1:
        raise ValueError("ambiguous route fingerprint: " + ", ".join(item[2] for item in tied))
    route = top[3]
    return _decision(route_id=top[2], fingerprint=fingerprint, route=route, entry_action=route.get("entry_action", "plan"), matched=True, reason="highest-specificity semantic route")


def _profile(fingerprint: dict[str, str], forced: str | None) -> str:
    if forced:
        return forced
    access = fingerprint.get("project_access")
    if access == "authorized":
        return "personal_full_control"
    if access == "restricted" and fingerprint.get("scope") == "safe_import":
        return "team_safe_import"
    return "generic_planning"
