"""Runtime-owned provider registry query surface."""
from __future__ import annotations

from pathlib import Path

from Runtime.Tooling.provider_contract import (
    ProviderDescriptor,
    ProviderRegistry,
    load_provider_registry,
)


class RuntimeProviderRegistry:
    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        *,
        root: Path | None = None,
    ) -> None:
        if registry is not None:
            self._registry = registry
        elif root is not None:
            self._registry = load_provider_registry(root=root)
        else:
            self._registry = load_provider_registry()

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    def provider(self, provider_id: str) -> ProviderDescriptor:
        try:
            return self._registry.providers[provider_id]
        except KeyError as exc:
            raise ValueError(f"unknown provider: {provider_id}") from exc

    def candidates(self, capability: str) -> tuple[ProviderDescriptor, ...]:
        if capability not in self._registry.capability_requirements:
            raise ValueError(f"unknown capability: {capability}")
        return tuple(
            provider
            for provider in self._registry.providers.values()
            if capability in provider.capabilities
        )
