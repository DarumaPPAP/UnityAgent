"""Typed Runtime Provider descriptor and registry validation.

This module owns provider metadata shape only. It does not select providers,
change Policy, or dispatch external tools.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path("Runtime/Tooling/provider_registry.yaml")
CAPABILITY_SCHEMA_PATH = Path("Runtime/Contracts/capability-request.schema.yaml")
ALLOWED_SURFACES = {"project", "host", "editor", "live_editor", "player"}
ALLOWED_TRANSPORTS = {"filesystem", "subprocess", "cli", "mcp", "player_bridge"}
ALLOWED_PROJECT_BINDING = {
    "canonical_project_root",
    "explicit_project_path",
    "environment_bound",
    "player_instance",
}
MAX_STRENGTH = 5


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False) -> dict:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


@dataclass(frozen=True)
class CapabilityOffer:
    capability: str
    priority: int
    surfaces: tuple[str, ...]
    evidence_supported: tuple[str, ...]
    environment_requirements: tuple[tuple[str, bool], ...]
    scope_preservation: bool


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    transport: str
    surfaces: tuple[str, ...]
    capabilities: dict[str, CapabilityOffer]
    health: str
    project_binding: str
    environment_key: str
    safety_strength: int
    evidence_strength: int


@dataclass(frozen=True)
class CapabilityRequirement:
    capability: str
    minimum_safety_strength: int
    minimum_evidence_strength: int


@dataclass(frozen=True)
class ProviderRegistry:
    providers: dict[str, ProviderDescriptor]
    capability_requirements: dict[str, CapabilityRequirement]


def _schema_vocab(root: Path) -> tuple[set[str], set[str]]:
    schema = yaml.safe_load((root / CAPABILITY_SCHEMA_PATH).read_text(encoding="utf-8")) or {}
    properties = schema.get("properties") or {}
    capabilities = set(((properties.get("capability") or {}).get("enum") or []))
    evidence = set(
        ((((properties.get("required_evidence") or {}).get("items") or {}).get("enum")) or [])
    )
    if not capabilities or not evidence:
        raise ValueError("CapabilityRequest schema vocabulary is incomplete")
    return {str(item) for item in capabilities}, {str(item) for item in evidence}


def _strength(value: Any, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_STRENGTH:
        raise ValueError(f"{label} must be an integer between 0 and {MAX_STRENGTH}")
    return value


def _string_list(value: Any, *, label: str, allowed: set[str] | None = None) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    result = tuple(str(item) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must not contain duplicates")
    if allowed is not None:
        unknown = set(result) - allowed
        if unknown:
            raise ValueError(f"{label} contains unknown values: {sorted(unknown)}")
    return result


def _parse_offer(
    capability: str,
    raw: Any,
    *,
    provider_surfaces: tuple[str, ...],
    known_evidence: set[str],
) -> CapabilityOffer:
    if not isinstance(raw, dict):
        raise ValueError(f"{capability}: provider capability offer must be a mapping")
    priority = raw.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool):
        raise ValueError(f"{capability}: priority must be an integer")
    surfaces = _string_list(
        raw.get("surfaces") or list(provider_surfaces),
        label=f"{capability}.surfaces",
        allowed=ALLOWED_SURFACES,
    )
    if not set(surfaces).issubset(set(provider_surfaces)):
        raise ValueError(f"{capability}: offer surfaces must be declared by provider")
    evidence_supported = _string_list(
        raw.get("evidence_supported"),
        label=f"{capability}.evidence_supported",
        allowed=known_evidence,
    )
    requirements = raw.get("environment_requirements") or {}
    if not isinstance(requirements, dict):
        raise ValueError(f"{capability}: environment_requirements must be a mapping")
    normalized_requirements: list[tuple[str, bool]] = []
    for path, expected in requirements.items():
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"{capability}: environment requirement path must be non-empty")
        if not isinstance(expected, bool):
            raise ValueError(f"{capability}: environment requirement values must be boolean")
        normalized_requirements.append((path, expected))
    scope_preservation = raw.get("scope_preservation")
    if not isinstance(scope_preservation, bool):
        raise ValueError(f"{capability}: scope_preservation must be boolean")
    return CapabilityOffer(
        capability=capability,
        priority=priority,
        surfaces=surfaces,
        evidence_supported=evidence_supported,
        environment_requirements=tuple(sorted(normalized_requirements)),
        scope_preservation=scope_preservation,
    )


def parse_provider_registry(value: Any, *, root: Path = ROOT) -> ProviderRegistry:
    if not isinstance(value, dict):
        raise ValueError("provider registry must be a mapping")
    if value.get("authority") != "Runtime":
        raise ValueError("provider registry authority must be Runtime")
    if value.get("provider_resolution_authority") is not True:
        raise ValueError("provider registry must explicitly declare Runtime provider resolution authority")
    if value.get("execution_dispatch_authority") is not False:
        raise ValueError("this registry stage must not enable execution dispatch authority")

    known_capabilities, known_evidence = _schema_vocab(root)
    raw_requirements = value.get("capability_requirements")
    if not isinstance(raw_requirements, dict):
        raise ValueError("capability_requirements must be a mapping")
    if set(raw_requirements) != known_capabilities:
        missing = sorted(known_capabilities - set(raw_requirements))
        extra = sorted(set(raw_requirements) - known_capabilities)
        raise ValueError(f"capability requirement vocabulary mismatch; missing={missing}, extra={extra}")

    requirements: dict[str, CapabilityRequirement] = {}
    for capability, raw in raw_requirements.items():
        if not isinstance(raw, dict):
            raise ValueError(f"{capability}: capability requirement must be a mapping")
        requirements[capability] = CapabilityRequirement(
            capability=capability,
            minimum_safety_strength=_strength(
                raw.get("minimum_safety_strength"),
                label=f"{capability}.minimum_safety_strength",
            ),
            minimum_evidence_strength=_strength(
                raw.get("minimum_evidence_strength"),
                label=f"{capability}.minimum_evidence_strength",
            ),
        )

    raw_providers = value.get("providers")
    if not isinstance(raw_providers, dict) or not raw_providers:
        raise ValueError("providers must be a non-empty mapping")

    providers: dict[str, ProviderDescriptor] = {}
    for provider_id, raw in raw_providers.items():
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider id must be a non-empty string")
        if not isinstance(raw, dict):
            raise ValueError(f"{provider_id}: provider descriptor must be a mapping")
        declared_id = raw.get("id")
        if declared_id != provider_id:
            raise ValueError(f"{provider_id}: descriptor id must match registry key")
        transport = str(raw.get("transport") or "")
        if transport not in ALLOWED_TRANSPORTS:
            raise ValueError(f"{provider_id}: unsupported transport {transport}")
        surfaces = _string_list(
            raw.get("surfaces"),
            label=f"{provider_id}.surfaces",
            allowed=ALLOWED_SURFACES,
        )
        health = str(raw.get("health") or "")
        if health != "environment_fact":
            raise ValueError(f"{provider_id}: health must use environment_fact in this stage")
        project_binding = str(raw.get("project_binding") or "")
        if project_binding not in ALLOWED_PROJECT_BINDING:
            raise ValueError(f"{provider_id}: unsupported project_binding {project_binding}")
        environment_key = str(raw.get("environment_key") or "")
        if not environment_key:
            raise ValueError(f"{provider_id}: environment_key is required")
        safety_strength = _strength(raw.get("safety_strength"), label=f"{provider_id}.safety_strength")
        evidence_strength = _strength(raw.get("evidence_strength"), label=f"{provider_id}.evidence_strength")

        raw_capabilities = raw.get("capabilities")
        if not isinstance(raw_capabilities, dict) or not raw_capabilities:
            raise ValueError(f"{provider_id}: capabilities must be a non-empty mapping")
        unknown_capabilities = set(raw_capabilities) - known_capabilities
        if unknown_capabilities:
            raise ValueError(f"{provider_id}: unknown capabilities {sorted(unknown_capabilities)}")
        capabilities = {
            capability: _parse_offer(
                capability,
                offer,
                provider_surfaces=surfaces,
                known_evidence=known_evidence,
            )
            for capability, offer in raw_capabilities.items()
        }
        providers[provider_id] = ProviderDescriptor(
            provider_id=provider_id,
            transport=transport,
            surfaces=surfaces,
            capabilities=capabilities,
            health=health,
            project_binding=project_binding,
            environment_key=environment_key,
            safety_strength=safety_strength,
            evidence_strength=evidence_strength,
        )

    for capability in known_capabilities:
        if not any(capability in provider.capabilities for provider in providers.values()):
            raise ValueError(f"{capability}: no provider advertises this capability")

    return ProviderRegistry(providers=providers, capability_requirements=requirements)


def load_provider_registry(path: Path | None = None, *, root: Path = ROOT) -> ProviderRegistry:
    registry_path = path or (root / REGISTRY_PATH)
    text = registry_path.read_text(encoding="utf-8")
    value = yaml.load(text, Loader=_UniqueKeyLoader)
    return parse_provider_registry(value, root=root)


def main() -> int:
    try:
        registry = load_provider_registry()
    except Exception as exc:  # noqa: BLE001 - canonical validator should report all contract failures.
        print(f"[ERROR] {REGISTRY_PATH}: {exc}")
        return 1
    print(
        "Provider registry validation: OK "
        f"({len(registry.providers)} providers, {len(registry.capability_requirements)} capabilities)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
