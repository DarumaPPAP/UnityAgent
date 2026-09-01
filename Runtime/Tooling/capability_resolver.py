"""Provider-independent capability resolution owned by Runtime.

Resolution is deterministic over CapabilityRequest + EnvironmentSnapshot +
explicit policy/approval context. It does not dispatch tools or semantically replan.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from math import inf
from typing import Any, Mapping

from Policy.Security.capability_policy import policy_for_capability
from Runtime.Contracts.capability_contract import (
    validate_capability_request,
    validate_capability_resolution,
)
from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.provider_contract import ProviderDescriptor, ProviderRegistry
from Runtime.Tooling.provider_registry import RuntimeProviderRegistry

HEALTH_SCORE = {"healthy": 2, "degraded": 1}
HARD_APPROVAL_REQUIREMENTS = {
    "required_for_project_asset_or_settings_change",
    "always_required",
}


@dataclass(frozen=True)
class ResolutionContext:
    """Runtime facts supplied by the Policy/Approval boundary.

    policy_allowed is deliberately required. Runtime must not assume Policy allowed
    an action merely because a provider exists.
    """

    policy_allowed: bool
    approval_complete: bool | None = None
    approval_required: bool | None = None
    provider_health: Mapping[str, str] | None = None
    provider_latency_ms: Mapping[str, float] | None = None


@dataclass(frozen=True)
class _Eligible:
    provider: ProviderDescriptor
    surface: str
    evidence_supported: tuple[str, ...]
    semantic_score: int
    health_score: int
    latency_ms: float


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    if hasattr(snapshot, "to_dict"):
        value = snapshot.to_dict()
    elif is_dataclass(snapshot):
        value = asdict(snapshot)
    else:
        value = snapshot
    if not isinstance(value, dict):
        raise ValueError("environment snapshot must be a mapping or EnvironmentSnapshot")
    return value


def _fact(snapshot: dict[str, Any], dotted_path: str) -> Any:
    current: Any = snapshot
    for segment in dotted_path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return "unknown"
        current = current[segment]
    return current


def _failure(
    *,
    capability: str,
    status: str,
    reason: str,
    evidence_supported: tuple[str, ...] = (),
) -> dict[str, Any]:
    value = {
        "schema_version": "1.0",
        "capability": capability,
        "status": status,
        "provider_ref": None,
        "observed_surface": None,
        "evidence_supported": list(evidence_supported),
        "failure_class": status,
        "reason": reason,
    }
    validate_capability_resolution(value)
    return value


def _resolved(
    *,
    capability: str,
    provider: ProviderDescriptor,
    surface: str,
    evidence_supported: tuple[str, ...],
) -> dict[str, Any]:
    value = {
        "schema_version": "1.0",
        "capability": capability,
        "status": "resolved",
        "provider_ref": provider.provider_id,
        "observed_surface": surface,
        "evidence_supported": list(evidence_supported),
        "failure_class": None,
        "reason": None,
    }
    validate_capability_resolution(value)
    return value


def _approval_block_reason(request: dict[str, Any], context: ResolutionContext) -> str | None:
    policy = policy_for_capability(str(request["capability"]))
    requirement = str(policy["approval_requirement"])
    hard_required = requirement in HARD_APPROVAL_REQUIREMENTS
    conditional_required = context.approval_required is True
    required = hard_required or conditional_required
    if not required:
        return None
    if not request.get("approval_ref"):
        return f"approval is required by Policy ({requirement}) but approval_ref is missing"
    if context.approval_complete is not True:
        return f"approval is required by Policy ({requirement}) but is not complete"
    return None


def _project_binding_failure(
    provider: ProviderDescriptor,
    snapshot: dict[str, Any],
    request_project_root: str,
) -> tuple[str, str] | None:
    snapshot_root = str(_fact(snapshot, "project.root") or "")
    if not snapshot_root or not same_project_root(request_project_root, snapshot_root):
        return "unavailable", "Environment Snapshot is not bound to the requested Project Root"

    identity_status = _fact(snapshot, "project.identity_status")
    if identity_status != "bound":
        return (
            "unknown" if identity_status == "unknown" else "unavailable",
            f"Project identity is not bound ({identity_status})",
        )

    if provider.project_binding == "environment_bound":
        status = _fact(snapshot, f"{provider.environment_key}.binding_status")
        if status == "ambiguous_binding":
            return "ambiguous_binding", f"{provider.provider_id} has ambiguous Project binding"
        if _fact(snapshot, f"{provider.environment_key}.project_bound") is not True:
            if status == "unknown":
                return "unknown", f"{provider.provider_id} Project binding is unknown"
            return "unavailable", f"{provider.provider_id} is not bound to the requested Project"
        if status != "bound":
            return "unavailable", f"{provider.provider_id} binding status is {status}"

    if provider.project_binding == "player_instance":
        reachable = _fact(snapshot, f"{provider.environment_key}.reachable")
        if reachable == "unknown":
            return "unknown", f"{provider.provider_id} reachability is unknown"
        if reachable is not True:
            return "unavailable", f"{provider.provider_id} is not reachable"

    return None


def _environment_failure(
    provider: ProviderDescriptor,
    capability: str,
    snapshot: dict[str, Any],
) -> tuple[str, str] | None:
    offer = provider.capabilities[capability]
    for path, expected in offer.environment_requirements:
        observed = _fact(snapshot, path)
        if observed == "unknown":
            return "unknown", f"{provider.provider_id}: environment fact {path} is unknown"
        if observed is not expected:
            return "unavailable", (
                f"{provider.provider_id}: environment fact {path}={observed!r}, "
                f"expected {expected!r}"
            )
    return None


def _choose_surface(provider: ProviderDescriptor, capability: str, preferred_surface: str | None) -> str:
    offer = provider.capabilities[capability]
    if preferred_surface and preferred_surface in offer.surfaces:
        return preferred_surface
    return offer.surfaces[0]


def _candidate_health(
    provider_id: str,
    context: ResolutionContext,
) -> tuple[str, int]:
    if context.provider_health is None or provider_id not in context.provider_health:
        return "healthy", HEALTH_SCORE["healthy"]
    value = str(context.provider_health[provider_id])
    if value in HEALTH_SCORE:
        return value, HEALTH_SCORE[value]
    if value in {"unhealthy", "unknown"}:
        return value, -1
    raise ValueError(f"{provider_id}: unsupported provider health value {value}")


def _fallback_floors(
    registry: ProviderRegistry,
    capability: str,
    fallback_from_provider_id: str | None,
) -> tuple[int, int]:
    requirement = registry.capability_requirements[capability]
    safety_floor = requirement.minimum_safety_strength
    evidence_floor = requirement.minimum_evidence_strength
    if fallback_from_provider_id is None:
        return safety_floor, evidence_floor
    previous = registry.providers.get(fallback_from_provider_id)
    if previous is None:
        raise ValueError(f"unknown fallback provider: {fallback_from_provider_id}")
    if capability not in previous.capabilities:
        raise ValueError(
            f"fallback provider {fallback_from_provider_id} did not provide capability {capability}"
        )
    return max(safety_floor, previous.safety_strength), max(
        evidence_floor, previous.evidence_strength
    )


def resolve_capability(
    request: dict[str, Any],
    environment_snapshot: Any,
    *,
    context: ResolutionContext,
    registry: ProviderRegistry | RuntimeProviderRegistry | None = None,
    fallback_from_provider_id: str | None = None,
) -> dict[str, Any]:
    """Resolve one CapabilityRequest to one safe Provider, or a typed failure."""
    validate_capability_request(request)
    capability = str(request["capability"])
    if not context.policy_allowed:
        return _failure(
            capability=capability,
            status="blocked_by_policy",
            reason="Policy did not allow this capability request",
        )

    approval_reason = _approval_block_reason(request, context)
    if approval_reason is not None:
        return _failure(
            capability=capability,
            status="blocked_by_approval",
            reason=approval_reason,
        )

    policy = policy_for_capability(capability)
    if policy["requires_mutation_scope"]:
        scope = request.get("mutation_scope")
        if not isinstance(scope, dict) or not scope.get("allowed_paths"):
            return _failure(
                capability=capability,
                status="scope_violation",
                reason="Mutation Scope is required and must contain allowed_paths",
            )

    runtime_registry = (
        registry
        if isinstance(registry, RuntimeProviderRegistry)
        else RuntimeProviderRegistry(registry=registry)
    )
    registry_value = runtime_registry.registry
    safety_floor, evidence_floor = _fallback_floors(
        registry_value, capability, fallback_from_provider_id
    )
    snapshot = _snapshot_dict(environment_snapshot)
    validate_environment_snapshot(snapshot)
    required_evidence = set(str(item) for item in request.get("required_evidence") or [])
    preferred_surface = request.get("preferred_surface")

    rejected_classes: list[str] = []
    rejected_reasons: list[str] = []
    eligible: list[_Eligible] = []

    for provider in runtime_registry.candidates(capability):
        if provider.provider_id == fallback_from_provider_id:
            continue
        offer = provider.capabilities[capability]

        binding_failure = _project_binding_failure(
            provider, snapshot, str(request["project_root"])
        )
        if binding_failure is not None:
            rejected_classes.append(binding_failure[0])
            rejected_reasons.append(binding_failure[1])
            continue

        environment_failure = _environment_failure(
            provider, capability, snapshot
        )
        if environment_failure is not None:
            rejected_classes.append(environment_failure[0])
            rejected_reasons.append(environment_failure[1])
            continue

        health, health_score = _candidate_health(provider.provider_id, context)
        if health == "unhealthy":
            rejected_classes.append("unhealthy")
            rejected_reasons.append(f"{provider.provider_id} health is unhealthy")
            continue
        if health == "unknown":
            rejected_classes.append("unknown")
            rejected_reasons.append(f"{provider.provider_id} health is unknown")
            continue

        if provider.safety_strength < safety_floor:
            rejected_classes.append("unsupported")
            rejected_reasons.append(
                f"{provider.provider_id} safety strength {provider.safety_strength} "
                f"is below required {safety_floor}"
            )
            continue
        if provider.evidence_strength < evidence_floor:
            rejected_classes.append("unsupported")
            rejected_reasons.append(
                f"{provider.provider_id} evidence strength {provider.evidence_strength} "
                f"is below required {evidence_floor}"
            )
            continue
        supported = set(offer.evidence_supported)
        if not required_evidence.issubset(supported):
            rejected_classes.append("unsupported")
            rejected_reasons.append(
                f"{provider.provider_id} cannot satisfy required evidence "
                f"{sorted(required_evidence - supported)}"
            )
            continue
        if policy["requires_mutation_scope"] and not offer.scope_preservation:
            rejected_classes.append("scope_violation")
            rejected_reasons.append(
                f"{provider.provider_id} does not preserve Mutation Scope for {capability}"
            )
            continue

        surface = _choose_surface(provider, capability, preferred_surface)
        surface_bonus = 5 if preferred_surface and preferred_surface in offer.surfaces else 0
        semantic_score = offer.priority + surface_bonus
        latency = inf
        if context.provider_latency_ms and provider.provider_id in context.provider_latency_ms:
            latency = float(context.provider_latency_ms[provider.provider_id])
            if latency < 0:
                raise ValueError(f"{provider.provider_id}: latency must be non-negative")
        eligible.append(
            _Eligible(
                provider=provider,
                surface=surface,
                evidence_supported=offer.evidence_supported,
                semantic_score=semantic_score,
                health_score=health_score,
                latency_ms=latency,
            )
        )

    if not eligible:
        if "ambiguous_binding" in rejected_classes:
            status = "ambiguous_binding"
        elif "scope_violation" in rejected_classes:
            status = "scope_violation"
        elif "unhealthy" in rejected_classes:
            status = "unhealthy"
        elif "unknown" in rejected_classes:
            status = "unknown"
        elif "unsupported" in rejected_classes:
            status = "unsupported"
        else:
            status = "unavailable"
        reason = "; ".join(rejected_reasons[:4]) or f"No provider offers capability {capability}"
        return _failure(capability=capability, status=status, reason=reason)

    # Eligibility is a hard gate. Ranking only runs after every safety/evidence/
    # binding constraint above has been satisfied.
    eligible.sort(
        key=lambda item: (
            item.semantic_score,
            item.health_score,
            -item.latency_ms,
        ),
        reverse=True,
    )
    winner = eligible[0]
    winner_rank = (
        winner.semantic_score,
        winner.health_score,
        winner.latency_ms,
    )
    tied = [
        item
        for item in eligible
        if (
            item.semantic_score,
            item.health_score,
            item.latency_ms,
        )
        == winner_rank
    ]
    if len(tied) > 1:
        return _failure(
            capability=capability,
            status="ambiguous_binding",
            reason=(
                "Provider ranking remained ambiguous after capability priority, "
                "preferred surface, health, and latency tie-breaks: "
                + ", ".join(sorted(item.provider.provider_id for item in tied))
            ),
        )

    return _resolved(
        capability=capability,
        provider=winner.provider,
        surface=winner.surface,
        evidence_supported=winner.evidence_supported,
    )
