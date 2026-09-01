"""Runtime Tool Broker Core.

The broker resolves provider identity only. Execution/dispatch remains a separate
Runtime concern and semantic replanning remains in Orchestration.
"""
from __future__ import annotations

from Runtime.Tooling.capability_resolver import ResolutionContext, resolve_capability
from Runtime.Tooling.provider_contract import ProviderRegistry
from Runtime.Tooling.provider_registry import RuntimeProviderRegistry


class ToolBroker:
    def __init__(self, registry: ProviderRegistry | RuntimeProviderRegistry | None = None) -> None:
        self._registry = (
            registry
            if isinstance(registry, RuntimeProviderRegistry)
            else RuntimeProviderRegistry(registry=registry)
        )

    def resolve(
        self,
        request: dict,
        environment_snapshot,
        *,
        context: ResolutionContext,
    ) -> dict:
        return resolve_capability(
            request,
            environment_snapshot,
            context=context,
            registry=self._registry,
        )

    def resolve_fallback(
        self,
        request: dict,
        environment_snapshot,
        *,
        context: ResolutionContext,
        previous_provider_id: str,
    ) -> dict:
        """Resolve an infrastructure fallback without weakening safety/evidence floors."""
        return resolve_capability(
            request,
            environment_snapshot,
            context=context,
            registry=self._registry,
            fallback_from_provider_id=previous_provider_id,
        )
