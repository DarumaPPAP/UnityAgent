"""Fallback safety/evidence strength comparison.

Runtime owns provider comparison. This module never selects a provider or changes
Policy; it only checks that a proposed infrastructure fallback is not weaker than
the provider that failed and still satisfies the requested evidence contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from Runtime.Tooling.provider_contract import ProviderRegistry
from Runtime.Tooling.provider_registry import RuntimeProviderRegistry


@dataclass(frozen=True)
class StrengthCheck:
    allowed: bool
    failure_class: str | None
    reason: str | None
    previous_safety: int
    candidate_safety: int
    previous_evidence: int
    candidate_evidence: int
    required_evidence: tuple[str, ...]
    candidate_evidence_supported: tuple[str, ...]


def _registry_value(
    registry: ProviderRegistry | RuntimeProviderRegistry | None,
) -> ProviderRegistry:
    if isinstance(registry, RuntimeProviderRegistry):
        return registry.registry
    return RuntimeProviderRegistry(registry=registry).registry


def compare_fallback_strength(
    *,
    capability: str,
    previous_provider_id: str,
    candidate_provider_id: str,
    required_evidence: Iterable[str],
    registry: ProviderRegistry | RuntimeProviderRegistry | None = None,
) -> StrengthCheck:
    """Return a fail-closed comparison for one same-capability fallback candidate."""
    value = _registry_value(registry)
    previous = value.providers.get(previous_provider_id)
    candidate = value.providers.get(candidate_provider_id)
    if previous is None:
        raise ValueError(f"unknown previous provider: {previous_provider_id}")
    if candidate is None:
        raise ValueError(f"unknown candidate provider: {candidate_provider_id}")
    if capability not in previous.capabilities:
        raise ValueError(
            f"{previous_provider_id} does not advertise capability {capability}"
        )
    if capability not in candidate.capabilities:
        return StrengthCheck(
            False,
            "unsupported",
            f"{candidate_provider_id} does not advertise capability {capability}",
            previous.safety_strength,
            candidate.safety_strength,
            previous.evidence_strength,
            candidate.evidence_strength,
            tuple(sorted(set(str(item) for item in required_evidence))),
            (),
        )

    required = tuple(sorted(set(str(item) for item in required_evidence)))
    supported = tuple(candidate.capabilities[capability].evidence_supported)
    missing = sorted(set(required) - set(supported))

    reason: str | None = None
    failure_class: str | None = None
    if candidate.safety_strength < previous.safety_strength:
        failure_class = "unsupported"
        reason = (
            f"fallback safety strength would weaken from "
            f"{previous.safety_strength} to {candidate.safety_strength}"
        )
    elif candidate.evidence_strength < previous.evidence_strength:
        failure_class = "unsupported"
        reason = (
            f"fallback evidence strength would weaken from "
            f"{previous.evidence_strength} to {candidate.evidence_strength}"
        )
    elif missing:
        failure_class = "unsupported"
        reason = f"fallback cannot satisfy required evidence: {missing}"
    elif not candidate.capabilities[capability].scope_preservation:
        failure_class = "scope_violation"
        reason = f"{candidate_provider_id} does not preserve mutation scope"

    return StrengthCheck(
        allowed=reason is None,
        failure_class=failure_class,
        reason=reason,
        previous_safety=previous.safety_strength,
        candidate_safety=candidate.safety_strength,
        previous_evidence=previous.evidence_strength,
        candidate_evidence=candidate.evidence_strength,
        required_evidence=required,
        candidate_evidence_supported=supported,
    )
