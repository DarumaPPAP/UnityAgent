"""Generic SubAgent Definition/Profile catalog for the canonical Runtime.

The catalog is the only place where a concrete specialist's identity, scope and
evidence vocabulary is declared.  Contract and Runtime code consumes a profile
without importing a product-specific provider or assuming a Unity component.
The first profile is UnityArtistCLI for compatibility with the v1.1 wire format.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


class ProfileValidationError(ValueError):
    """A SubAgent profile is incomplete, ambiguous or unsafe."""


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileValidationError(f"{name} must be a non-empty string")
    return value


def _unique_texts(value: Any, name: str, *, minimum: int = 1) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ProfileValidationError(f"{name} must be a list with at least {minimum} item(s)")
    result = tuple(_text(item, f"{name} item") for item in value)
    if len(set(result)) != len(result):
        raise ProfileValidationError(f"{name} must not contain duplicates")
    return result


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileValidationError(f"{name} must be an object")
    return dict(value)


@dataclass(frozen=True)
class SubAgentProfile:
    """Declarative contract capabilities for one concrete SubAgent.

    A profile is data, not a second execution framework.  All mutation and
    evidence gates remain the canonical classes in this package.
    """

    profile_id: str
    display_name: str
    provider_id: str
    audience: str
    goal_type: str
    capabilities: tuple[str, ...]
    primary_capability: str
    required_evidence: tuple[str, ...]
    scope: dict[str, Any]
    value: dict[str, Any]
    approval: dict[str, Any]
    evidence: dict[str, str]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SubAgentProfile":
        data = _mapping(value, "SubAgentProfile")
        required = {
            "profile_id", "display_name", "provider_id", "audience", "goal_type",
            "capabilities", "primary_capability", "required_evidence", "scope",
            "value", "approval", "evidence",
        }
        unknown = set(data) - required
        missing = required - set(data)
        if missing or unknown:
            raise ProfileValidationError(
                f"SubAgentProfile fields mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        capabilities = _unique_texts(data["capabilities"], "capabilities")
        evidence_types = _unique_texts(data["required_evidence"], "required_evidence")
        primary = _text(data["primary_capability"], "primary_capability")
        if primary not in capabilities:
            raise ProfileValidationError("primary_capability must be included in capabilities")
        scope = _mapping(data["scope"], "scope")
        scope_required = {"default_target_guid", "component_type", "property_paths", "mutation_channels", "max_targets"}
        if set(scope) != scope_required:
            raise ProfileValidationError("profile scope fields are not exact")
        if not isinstance(scope["max_targets"], int) or isinstance(scope["max_targets"], bool) or scope["max_targets"] < 1:
            raise ProfileValidationError("scope.max_targets must be a positive integer")
        scope = {
            "default_target_guid": _text(scope["default_target_guid"], "scope.default_target_guid"),
            "component_type": _text(scope["component_type"], "scope.component_type"),
            "property_paths": list(_unique_texts(scope["property_paths"], "scope.property_paths")),
            "mutation_channels": list(_unique_texts(scope["mutation_channels"], "scope.mutation_channels")),
            "max_targets": scope["max_targets"],
        }
        value_spec = _mapping(data["value"], "value")
        if set(value_spec) != {"type", "unit", "minimum", "maximum", "maximum_exclusive"}:
            raise ProfileValidationError("profile value fields are not exact")
        if not isinstance(value_spec["minimum"], (int, float)) or isinstance(value_spec["minimum"], bool):
            raise ProfileValidationError("value.minimum must be numeric")
        if not isinstance(value_spec["maximum"], (int, float)) or isinstance(value_spec["maximum"], bool):
            raise ProfileValidationError("value.maximum must be numeric")
        if float(value_spec["minimum"]) >= float(value_spec["maximum"]):
            raise ProfileValidationError("value minimum must be below maximum")
        value_spec = {
            "type": _text(value_spec["type"], "value.type"),
            "unit": _text(value_spec["unit"], "value.unit"),
            "minimum": float(value_spec["minimum"]),
            "maximum": float(value_spec["maximum"]),
            "maximum_exclusive": bool(value_spec["maximum_exclusive"]),
        }
        approval_spec = _mapping(data["approval"], "approval")
        if set(approval_spec) != {"default_minimum", "default_maximum", "minimum_exclusive", "maximum_exclusive"}:
            raise ProfileValidationError("profile approval fields are not exact")
        for key in ("default_minimum", "default_maximum"):
            if not isinstance(approval_spec[key], (int, float)) or isinstance(approval_spec[key], bool):
                raise ProfileValidationError(f"approval.{key} must be numeric")
        if float(approval_spec["default_minimum"]) > float(approval_spec["default_maximum"]):
            raise ProfileValidationError("approval default minimum must not exceed maximum")
        approval_spec = {
            "default_minimum": float(approval_spec["default_minimum"]),
            "default_maximum": float(approval_spec["default_maximum"]),
            "minimum_exclusive": bool(approval_spec["minimum_exclusive"]),
            "maximum_exclusive": bool(approval_spec["maximum_exclusive"]),
        }
        evidence = _mapping(data["evidence"], "evidence")
        if set(evidence) != {"source_type", "producer", "provenance_token"}:
            raise ProfileValidationError("profile evidence fields are not exact")
        evidence = {key: _text(evidence[key], f"evidence.{key}") for key in evidence}
        return cls(
            profile_id=_text(data["profile_id"], "profile_id"),
            display_name=_text(data["display_name"], "display_name"),
            provider_id=_text(data["provider_id"], "provider_id"),
            audience=_text(data["audience"], "audience"),
            goal_type=_text(data["goal_type"], "goal_type"),
            capabilities=capabilities,
            primary_capability=primary,
            required_evidence=evidence_types,
            scope=scope,
            value=value_spec,
            approval=approval_spec,
            evidence=evidence,
        )

    @property
    def default_scope(self) -> dict[str, Any]:
        return {
            "target_guids": [self.scope["default_target_guid"]],
            "component_type": self.scope["component_type"],
            "property_paths": list(self.scope["property_paths"]),
            "mutation_channels": list(self.scope["mutation_channels"]),
        }

    @property
    def action_property_path(self) -> str:
        if len(self.scope["property_paths"]) != 1:
            raise ProfileValidationError("TypedAction requires a profile with one canonical property path")
        return str(self.scope["property_paths"][0])

    @property
    def action_mutation_channel(self) -> str:
        if len(self.scope["mutation_channels"]) != 1:
            raise ProfileValidationError("TypedAction requires a profile with one canonical mutation channel")
        return str(self.scope["mutation_channels"][0])

    def validate_scope(self, value: Mapping[str, Any]) -> dict[str, Any]:
        data = _mapping(value, "scope")
        required = {"target_guids", "component_type", "property_paths", "mutation_channels"}
        if set(data) != required:
            raise ProfileValidationError("scope fields are not exact")
        targets = _unique_texts(data["target_guids"], "scope.target_guids")
        if len(targets) > int(self.scope["max_targets"]):
            raise ProfileValidationError("scope.target_guids exceeds the profile target limit")
        paths = _unique_texts(data["property_paths"], "scope.property_paths")
        channels = _unique_texts(data["mutation_channels"], "scope.mutation_channels")
        if tuple(paths) != tuple(self.scope["property_paths"]):
            raise ProfileValidationError("scope.property_paths is outside the SubAgent profile")
        if tuple(channels) != tuple(self.scope["mutation_channels"]):
            raise ProfileValidationError("scope.mutation_channels is outside the SubAgent profile")
        if data["component_type"] != self.scope["component_type"]:
            raise ProfileValidationError("scope.component_type is outside the SubAgent profile")
        return {"target_guids": list(targets), "component_type": data["component_type"], "property_paths": list(paths), "mutation_channels": list(channels)}

    def validate_capabilities(self, values: list[str] | tuple[str, ...], *, require_primary: bool = True) -> list[str]:
        result = list(_unique_texts(list(values), "capabilities"))
        if any(item not in self.capabilities for item in result):
            raise ProfileValidationError("capability is outside the SubAgent profile")
        if require_primary and self.primary_capability not in result:
            raise ProfileValidationError("capability set does not include the profile primary capability")
        return result

    def validate_value(self, value: float) -> float:
        number = float(value)
        lower = float(self.value["minimum"])
        upper = float(self.value["maximum"])
        if number < lower or (self.value["maximum_exclusive"] and number >= upper) or (not self.value["maximum_exclusive"] and number > upper):
            raise ProfileValidationError("TypedAction value is outside the SubAgent profile range")
        return number

    def validate_parameter_envelope(self, value: Mapping[str, Any]) -> dict[str, float]:
        data = _mapping(value, "parameter_envelope")
        if set(data) != {"min", "max"}:
            raise ProfileValidationError("parameter_envelope fields are not exact")
        lower, upper = float(data["min"]), float(data["max"])
        minimum = float(self.value["minimum"])
        maximum = float(self.value["maximum"])
        if lower > upper or lower < minimum or upper > maximum or (self.approval["minimum_exclusive"] and lower <= minimum) or (self.approval["maximum_exclusive"] and upper >= maximum):
            raise ProfileValidationError("parameter envelope is outside the SubAgent profile range")
        return {"min": lower, "max": upper}


@dataclass(frozen=True)
class SubAgentDefinition:
    """Catalog entry grouping a profile with its canonical session contract."""

    profile: SubAgentProfile
    contract_revision: str = "1.1"
    session_entrypoint: str = "Runtime.ReferenceImplementation.specialist_child"

    @property
    def definition_id(self) -> str:
        return self.profile.profile_id


class SubAgentProfileCatalog:
    def __init__(self, definitions: Mapping[str, SubAgentDefinition], *, default_profile_id: str) -> None:
        if not definitions or default_profile_id not in definitions:
            raise ProfileValidationError("profile catalog must contain its default profile")
        self._definitions = dict(definitions)
        self.default_profile_id = default_profile_id

    @classmethod
    def from_file(cls, path: str | Path) -> "SubAgentProfileCatalog":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        data = _mapping(raw, "SubAgentProfileCatalog")
        if data.get("schema_version") != "1.0":
            raise ProfileValidationError("profile catalog schema_version must be 1.0")
        profiles = _mapping(data.get("profiles"), "profiles")
        definitions = {key: SubAgentDefinition(SubAgentProfile.from_mapping(value)) for key, value in profiles.items()}
        if any(key != definition.profile.profile_id for key, definition in definitions.items()):
            raise ProfileValidationError("profile catalog key must equal profile_id")
        return cls(definitions, default_profile_id=_text(data.get("default_profile"), "default_profile"))

    def get(self, profile_id: str) -> SubAgentProfile:
        try:
            return self._definitions[profile_id].profile
        except KeyError as exc:
            raise ProfileValidationError(f"unknown SubAgent profile: {profile_id}") from exc

    def definition(self, profile_id: str) -> SubAgentDefinition:
        try:
            return self._definitions[profile_id]
        except KeyError as exc:
            raise ProfileValidationError(f"unknown SubAgent definition: {profile_id}") from exc

    def resolve_goal(self, goal_type: str) -> SubAgentProfile:
        matches = [definition.profile for definition in self._definitions.values() if definition.profile.goal_type == goal_type]
        if len(matches) != 1:
            raise ProfileValidationError(f"goal_type does not resolve to exactly one SubAgent profile: {goal_type}")
        return matches[0]

    def resolve_capability(self, capability: str) -> SubAgentProfile:
        matches = [definition.profile for definition in self._definitions.values() if capability in definition.profile.capabilities]
        if len(matches) != 1:
            raise ProfileValidationError(f"capability does not resolve to exactly one SubAgent profile: {capability}")
        return matches[0]

    def resolve_grant(self, audience: str, capabilities: list[str] | tuple[str, ...]) -> SubAgentProfile:
        matches = [
            definition.profile for definition in self._definitions.values()
            if definition.profile.audience == audience and all(item in definition.profile.capabilities for item in capabilities)
        ]
        if len(matches) != 1:
            raise ProfileValidationError("SurfaceGrant does not resolve to exactly one SubAgent profile")
        return matches[0]

    def evidence_types(self) -> frozenset[str]:
        return frozenset(item for definition in self._definitions.values() for item in definition.profile.required_evidence)

    def definitions(self) -> tuple[SubAgentDefinition, ...]:
        return tuple(self._definitions.values())


CATALOG = SubAgentProfileCatalog.from_file(Path(__file__).with_name("subagent-catalog.yaml"))


def default_profile() -> SubAgentProfile:
    return CATALOG.get(CATALOG.default_profile_id)


def profile_for_task(value: Mapping[str, Any]) -> SubAgentProfile:
    return CATALOG.resolve_goal(_text(value.get("goal_type"), "goal_type"))


def profile_for_capability(value: Mapping[str, Any]) -> SubAgentProfile:
    return CATALOG.resolve_capability(_text(value.get("capability"), "capability"))


def profile_for_grant(value: Mapping[str, Any]) -> SubAgentProfile:
    return CATALOG.resolve_grant(_text(value.get("audience"), "audience"), list(value.get("capabilities") or []))


def profile_for_task_object(task: Any) -> SubAgentProfile:
    return profile_for_task({"goal_type": task.goal_type})
