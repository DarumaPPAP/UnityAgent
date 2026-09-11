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

    def resolve_management(self, operation: str, *, project_root: str) -> dict[str, Any]:
        """Resolve one Control Plane management operation through the same Registry."""
        candidates = self._registry.management_candidates(operation)
        if len(candidates) != 1:
            status = "unavailable" if not candidates else "ambiguous_binding"
            return {
                "schema_version": "1.0",
                "operation": operation,
                "status": status,
                "provider_ref": None,
                "observed_surface": "host",
                "evidence_supported": ["install_receipt", "toolchain_observation"],
                "failure_class": status,
                "reason": "expected exactly one enabled management Provider",
            }
        provider = candidates[0]
        return {
            "schema_version": "1.0",
            "operation": operation,
            "status": "resolved",
            "provider_ref": provider.provider_id,
            "observed_surface": "host",
            "evidence_supported": ["install_receipt", "toolchain_observation"],
            "failure_class": None,
            "reason": None,
            "project_root": str(project_root),
        }

    def dispatch_management(
        self,
        request: Mapping[str, Any],
        *,
        executors: Mapping[str, Any],
        executor_arguments: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch setup only after Registry resolution; Entry never supplies provider id."""
        operation = str(request.get("operation") or "")
        project_root = str(request.get("project_root") or "")
        resolution = self.resolve_management(operation, project_root=project_root)
        if resolution.get("status") != "resolved":
            return {"schema_version": "1.0", "status": "blocked", "resolution": resolution, "provider_result": None}
        provider_ref = str(resolution["provider_ref"])
        executor = executors.get(provider_ref)
        if executor is None:
            return {
                "schema_version": "1.0",
                "status": "blocked",
                "resolution": resolution,
                "provider_result": {
                    "schema_version": "1.0",
                    "operation": operation,
                    "status": "failed",
                    "failure_class": "backend_not_implemented",
                    "reason": f"no management executor registered for {provider_ref}",
                },
            }
        try:
            result = executor(request, **dict(executor_arguments or {}))
        except (OSError, PermissionError, ConnectionError) as exc:
            result = {
                "schema_version": "1.0",
                "operation": operation,
                "status": "failed",
                "failure_class": "unhealthy",
                "reason": str(exc),
            }
        if not isinstance(result, dict):
            result = {
                "schema_version": "1.0",
                "operation": operation,
                "status": "failed",
                "failure_class": "not_observed",
                "reason": "management Provider did not return a structured result",
            }
        result.setdefault("provider_ref", provider_ref)
        return {
            "schema_version": "1.0",
            "status": "completed" if result.get("status") == "passed" else "blocked",
            "resolution": resolution,
            "provider_result": result,
        }

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
