"""Deterministic semantic route selection. Context materialization consumes this decision; it does not make it."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from Runtime.Tooling.Environment.project_identity import same_project_root

REQUIRED_DIMENSIONS = ("intent", "artifact", "scope", "failure_mode", "architecture_state", "mutation_target", "evidence_state", "project_access")
DESIGN_REVIEW_REQUIREMENTS = {"required", "conditional", "not_required"}


def task_fingerprint_from_intent(intent: dict[str, Any], environment_snapshot: dict[str, Any], *, project_root: str, policy_allowed: bool) -> dict[str, str]:
    """Project the two read-only Pilot intents; only observed binding and Policy grant access."""
    kind = intent.get("kind")
    if kind == "project_inspection" and set(intent) == {"kind"}:
        fingerprint = {"intent": "review", "artifact": "project", "scope": "read_only",
            "failure_mode": "none", "architecture_state": "not_applicable",
            "mutation_target": "none", "evidence_state": "unknown"}
    elif kind == "visual_capture" and set(intent) == {
            "kind", "visual_intent", "exact_scene_or_asset_scope", "reference_or_visual_definition"} and all(
            isinstance(intent[key], str) and intent[key].strip() for key in (
                "visual_intent", "exact_scene_or_asset_scope", "reference_or_visual_definition")):
        fingerprint = {"intent": "review", "artifact": "visual", "scope": "project_asset",
            "failure_mode": "none", "architecture_state": "not_applicable",
            "mutation_target": "none", "evidence_state": "not_applicable"}
    elif kind == "rendering_diagnosis" and set(intent).issubset({"kind", "symptom", "target_scope", "change_requested"}) and all(isinstance(intent.get(key), str) and intent[key].strip() for key in ("symptom", "target_scope")) and isinstance(intent.get("change_requested", False), bool):
        fingerprint = {"intent": "fix" if intent.get("change_requested") else "investigate", "artifact": "rendering", "scope": "local", "failure_mode": "rendering_unknown", "architecture_state": "not_applicable", "mutation_target": "source" if intent.get("change_requested") else "none", "evidence_state": "unknown"}
    else:
        raise ValueError("unsupported or incomplete read-only Typed Intent")
    project = environment_snapshot.get("project") or {}
    if (not policy_allowed or project.get("identity_status") != "bound"
            or not project.get("root") or not same_project_root(project_root, str(project["root"]))):
        raise ValueError("project access is not authorized by bound EnvironmentSnapshot and Policy")
    fingerprint["project_access"] = "authorized"
    return fingerprint


def load_routes(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("authority") != "Orchestration":
        raise ValueError("task route catalog must be Orchestration authority")
    for route_id, route in (data.get("routes") or {}).items():
        requirement = route.get("design_review", "not_required")
        if requirement not in DESIGN_REVIEW_REQUIREMENTS:
            raise ValueError(f"invalid design_review requirement for {route_id}: {requirement}")
        if route.get("specialist_pilot") and (not route.get("specialist_profile") or route.get("specialist_phase") != "analysis"):
            raise ValueError(f"candidate Specialist route must declare analysis phase: {route_id}")
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


def resolve_specialist(route_id: str, capability: str, environment_snapshot: Any, *, root: Path | None = None, pilot_enabled: bool = False, requested_mutation: bool = False, specialist_capability_mutates: bool = False, context_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Resolve semantic analysis ownership; requested_mutation is Task intent, not Specialist authority."""
    from Runtime.ReferenceImplementation.profiles import CATALOG, ProfileValidationError

    repository = root or Path(__file__).resolve().parents[2]
    route = load_routes(repository / "Orchestration/Routing/task-routes.yaml").get("routes", {}).get(route_id)
    if route is None:
        raise ValueError(f"unknown route: {route_id}")
    profile_id = route.get("specialist_profile")
    if profile_id is None:
        return {"status": "not_required", "profile_id": None, "capability": capability}
    if route.get("specialist_pilot"):
        from Runtime.ReferenceImplementation.candidate_profiles import load_candidate_profile, resolve_candidate
        snapshot = environment_snapshot.to_dict() if hasattr(environment_snapshot, "to_dict") else environment_snapshot
        profile = load_candidate_profile(profile_id, root=repository)
        return resolve_candidate(profile, capability, snapshot, pilot_enabled=pilot_enabled, specialist_capability_mutates=specialist_capability_mutates, context_items=context_items)
    try:
        profile = CATALOG.resolve_capability(capability)
    except ProfileValidationError:
        return {"status": "unsupported", "profile_id": None, "capability": capability}
    if profile.profile_id != profile_id:
        return {"status": "unsupported", "profile_id": None, "capability": capability}
    if profile.eligibility_failure(environment_snapshot) is not None:
        return {"status": "unavailable", "profile_id": None, "capability": capability}
    return {"status": "selected", "profile_id": profile.profile_id, "capability": capability,
            "required_evidence": list(profile.required_evidence)}


def select_specialist_capability(route_id: str, requests: list[dict[str, Any]], *, root: Path | None = None) -> str | None:
    """Intersect route requests with the bound Specialist Profile; never choose by order."""
    from Runtime.ReferenceImplementation.profiles import CATALOG
    from Runtime.ReferenceImplementation.candidate_profiles import load_candidate_profile

    repository = root or Path(__file__).resolve().parents[2]
    route = load_routes(repository / "Orchestration/Routing/task-routes.yaml").get("routes", {}).get(route_id)
    if route is None:
        raise ValueError(f"unknown route: {route_id}")
    profile_id = route.get("specialist_profile")
    if profile_id is None:
        # Core routes have no Specialist phase to select.
        return None
    if route.get("specialist_pilot"):
        capabilities = set(load_candidate_profile(profile_id, root=repository)["capabilities"])
    else:
        profiles = [item.profile for item in CATALOG.definitions() if item.profile.profile_id == profile_id]
        if len(profiles) != 1:
            raise ValueError(f"unknown Specialist Profile: {profile_id}")
        capabilities = set(profiles[0].capabilities)
    matches = {str(request["capability"]) for request in requests if request.get("capability") in capabilities}
    if not matches:
        raise ValueError(f"no specialist capability match: {route_id}")
    if len(matches) != 1:
        raise ValueError(f"ambiguous specialist capability: {sorted(matches)}")
    return next(iter(matches))
