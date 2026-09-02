"""Canonical Production Runtime Tool Broker.

Orchestration supplies provider-independent CapabilityRequest values. The broker
owns provider resolution and the Production dispatch entrypoint; provider invocation
stays in Runtime/Dispatcher and semantic replanning stays in Orchestration.
"""
from __future__ import annotations

from typing import Any, Mapping

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

    @property
    def registry(self) -> RuntimeProviderRegistry:
        return self._registry

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

    def dispatch(
        self,
        request: dict[str, Any],
        environment_snapshot: Any,
        *,
        context: ResolutionContext,
        executors: Mapping[str, Any],
        provider_arguments: Mapping[str, Mapping[str, Any]] | None = None,
        maximum_retry_attempts: int = 1,
    ) -> dict[str, Any]:
        """Execute through the Production dispatcher after Broker-owned resolution."""
        # Local import prevents the Dispatcher/FallbackPolicy/ToolBroker dependency
        # graph from becoming an import-time cycle while preserving one public owner.
        from Runtime.Dispatcher.tool_runtime_dispatcher import dispatch_capability

        return dispatch_capability(
            self,
            request,
            environment_snapshot,
            context=context,
            executors=executors,
            provider_arguments=provider_arguments,
            maximum_retry_attempts=maximum_retry_attempts,
        )
