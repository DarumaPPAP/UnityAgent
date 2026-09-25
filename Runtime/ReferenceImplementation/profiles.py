"""Generic SubAgent Definition/Profile catalog for the canonical Runtime.

The catalog is the only place where a concrete specialist's identity, scope and
evidence vocabulary is declared.  Contract and Runtime code consumes a profile
without importing a product-specific provider or assuming a Unity component.
The first profile is ArtistSubAgent. Its provider_id identifies only the execution backend; the SubAgent identity is profile_id.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Any, Mapping

import yaml


class ProfileValidationError(ValueError):
    """A SubAgent profile is incomplete, ambiguous or unsafe."""


def runtime_profile_revision(root: str | Path | None = None) -> str:
    """Provider RegistryとSubAgent Catalogを既存Fingerprintの一つのRevisionへ束ねる。"""
    project_root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[2]
    relative_paths = (
        "Runtime/Tooling/provider_registry.yaml",
        "Runtime/ReferenceImplementation/subagent-catalog.yaml",
    )
    digest = hashlib.sha256()
    for relative in relative_paths:
        path = project_root / relative
        try:
            content = path.read_bytes()
        except OSError:
            return f"missing:{relative}"
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()[:16]


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


def _finite_number(value: Any, name: str) -> float:
    """Accept only finite JSON/YAML numbers at the profile boundary."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ProfileValidationError(f"{name} must be numeric")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ProfileValidationError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ProfileValidationError(f"{name} must be a finite number")
    return number


def _snapshot_mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    return _mapping(value, "environment_snapshot")


def _fact(snapshot: Mapping[str, Any], dotted_path: str) -> Any:
    current: Any = snapshot
    for segment in dotted_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return "unknown"
        current = current[segment]
    return current


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
    activation: dict[str, Any]
    scope: dict[str, Any]
    value: dict[str, Any]
    approval: dict[str, Any]
    evidence: dict[str, str]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, catalog_version: str = "1.0") -> "SubAgentProfile":
        data = _mapping(value, "SubAgentProfile")
        if any(not isinstance(key, str) for key in data):
            raise ProfileValidationError("SubAgentProfile field names must be strings")
        required = {
            "profile_id", "display_name", "provider_id", "audience", "goal_type",
            "capabilities", "primary_capability", "required_evidence", "activation", "scope",
            "value", "approval", "evidence",
        }
        if catalog_version == "2.0":
            required -= {"scope", "value", "approval"}
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
        activation = _mapping(data["activation"], "activation")
        if set(activation) != {"install_mode", "auto_install", "required_environment"}:
            raise ProfileValidationError("profile activation fields are not exact")
        if activation["install_mode"] != "optional":
            raise ProfileValidationError("SubAgent install_mode must be optional")
        if activation["auto_install"] is not False:
            raise ProfileValidationError("SubAgent auto_install must remain false")
        activation = {
            "install_mode": "optional",
            "auto_install": False,
            "required_environment": list(_unique_texts(activation["required_environment"], "activation.required_environment")),
        }
        if catalog_version == "2.0":
            evidence = _mapping(data["evidence"], "evidence")
            if set(evidence) != {"source_type", "producer", "provenance_token"}:
                raise ProfileValidationError("profile evidence fields are not exact")
            return cls(profile_id=_text(data["profile_id"], "profile_id"),
                display_name=_text(data["display_name"], "display_name"),
                provider_id=_text(data["provider_id"], "provider_id"),
                audience=_text(data["audience"], "audience"),
                goal_type=_text(data["goal_type"], "goal_type"),
                capabilities=capabilities, primary_capability=primary, required_evidence=evidence_types,
                activation=activation, scope={}, value={}, approval={},
                evidence={key: _text(evidence[key], f"evidence.{key}") for key in evidence})
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
        minimum = _finite_number(value_spec["minimum"], "value.minimum")
        maximum = _finite_number(value_spec["maximum"], "value.maximum")
        if minimum >= maximum:
            raise ProfileValidationError("value minimum must be below maximum")
        if not isinstance(value_spec["maximum_exclusive"], bool):
            raise ProfileValidationError("value.maximum_exclusive must be boolean")
        value_spec = {
            "type": _text(value_spec["type"], "value.type"),
            "unit": _text(value_spec["unit"], "value.unit"),
            "minimum": minimum,
            "maximum": maximum,
            "maximum_exclusive": bool(value_spec["maximum_exclusive"]),
        }
        approval_spec = _mapping(data["approval"], "approval")
        if set(approval_spec) != {"default_minimum", "default_maximum", "minimum_exclusive", "maximum_exclusive"}:
            raise ProfileValidationError("profile approval fields are not exact")
        approval_minimum = _finite_number(approval_spec["default_minimum"], "approval.default_minimum")
        approval_maximum = _finite_number(approval_spec["default_maximum"], "approval.default_maximum")
        for key in ("minimum_exclusive", "maximum_exclusive"):
            if not isinstance(approval_spec[key], bool):
                raise ProfileValidationError(f"approval.{key} must be boolean")
        if approval_minimum > approval_maximum:
            raise ProfileValidationError("approval default minimum must not exceed maximum")
        approval_spec = {
            "default_minimum": approval_minimum,
            "default_maximum": approval_maximum,
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
            activation=activation,
            scope=scope,
            value=value_spec,
            approval=approval_spec,
            evidence=evidence,
        )

    def to_mapping(self) -> dict[str, Any]:
        """既存UnityAgent ProfileCatalogのwire形式へ正規化して返す。"""
        result = {
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "provider_id": self.provider_id,
            "audience": self.audience,
            "goal_type": self.goal_type,
            "capabilities": list(self.capabilities),
            "primary_capability": self.primary_capability,
            "required_evidence": list(self.required_evidence),
            "activation": {
                "install_mode": self.activation["install_mode"],
                "auto_install": self.activation["auto_install"],
                "required_environment": list(self.activation["required_environment"]),
            },
            "evidence": dict(self.evidence),
        }
        if self.scope:
            result.update(scope=dict(self.scope), value=dict(self.value), approval=dict(self.approval))
        return result

    @property
    def default_scope(self) -> dict[str, Any]:
        if not self.scope:
            raise ProfileValidationError("generic Specialist profile has no camera reference scope")
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

    def eligibility_failure(self, environment_snapshot: Any) -> tuple[str, str] | None:
        snapshot = _snapshot_mapping(environment_snapshot)
        for path in self.activation["required_environment"]:
            observed = _fact(snapshot, path)
            if observed is not True:
                status = "unknown" if observed == "unknown" else "unavailable"
                return status, f"{self.profile_id}: environment fact {path}={observed!r}; expected True"
        return None

    def require_eligible(self, environment_snapshot: Any) -> None:
        failure = self.eligibility_failure(environment_snapshot)
        if failure is not None:
            raise ProfileValidationError(f"SubAgent is not eligible ({failure[0]}): {failure[1]}")

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
        number = _finite_number(value, "value")
        lower = float(self.value["minimum"])
        upper = float(self.value["maximum"])
        if number < lower or (self.value["maximum_exclusive"] and number >= upper) or (not self.value["maximum_exclusive"] and number > upper):
            raise ProfileValidationError("TypedAction value is outside the SubAgent profile range")
        return number

    def validate_parameter_envelope(self, value: Mapping[str, Any]) -> dict[str, float]:
        data = _mapping(value, "parameter_envelope")
        if set(data) != {"min", "max"}:
            raise ProfileValidationError("parameter_envelope fields are not exact")
        lower = _finite_number(data["min"], "parameter_envelope.min")
        upper = _finite_number(data["max"], "parameter_envelope.max")
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
    def __init__(self, definitions: Mapping[str, SubAgentDefinition], *, default_profile_id: str, schema_version: str = "1.0") -> None:
        if not definitions or default_profile_id not in definitions:
            raise ProfileValidationError("profile catalog must contain its default profile")
        self._definitions = dict(definitions)
        self.default_profile_id = default_profile_id
        self.schema_version = schema_version

    @classmethod
    def from_file(cls, path: str | Path) -> "SubAgentProfileCatalog":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SubAgentProfileCatalog":
        data = _mapping(value, "SubAgentProfileCatalog")
        if set(data) != {"schema_version", "default_profile", "profiles"}:
            raise ProfileValidationError("SubAgentProfileCatalog fields are not exact")
        version = data.get("schema_version")
        if version not in {"1.0", "2.0"}:
            raise ProfileValidationError("profile catalog schema_version must be 1.0 or 2.0")
        profiles = _mapping(data.get("profiles"), "profiles")
        if any(not isinstance(key, str) or not key.strip() for key in profiles):
            raise ProfileValidationError("profile catalog profile keys must be non-empty strings")
        definitions = {key: SubAgentDefinition(SubAgentProfile.from_mapping(value, catalog_version=version)) for key, value in profiles.items()}
        if any(key != definition.profile.profile_id for key, definition in definitions.items()):
            raise ProfileValidationError("profile catalog key must equal profile_id")
        return cls(definitions, default_profile_id=_text(data.get("default_profile"), "default_profile"), schema_version=version)

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

    def available_definitions(self, environment_snapshot: Any) -> tuple[SubAgentDefinition, ...]:
        return tuple(
            definition
            for definition in self._definitions.values()
            if definition.profile.eligibility_failure(environment_snapshot) is None
        )

    def resolve_available_capability(self, capability: str, environment_snapshot: Any) -> SubAgentProfile:
        matches = [
            definition.profile
            for definition in self.available_definitions(environment_snapshot)
            if capability in definition.profile.capabilities
        ]
        if len(matches) != 1:
            raise ProfileValidationError(
                f"capability does not resolve to exactly one installed/eligible SubAgent profile: {capability}"
            )
        return matches[0]

    def evidence_types(self) -> frozenset[str]:
        return frozenset(item for definition in self._definitions.values() for item in definition.profile.required_evidence)

    def definitions(self) -> tuple[SubAgentDefinition, ...]:
        return tuple(self._definitions.values())

    def to_mapping(self) -> dict[str, Any]:
        """現在のCatalogを既存Snapshot形式へ正規化して返す。"""
        return {
            "schema_version": self.schema_version,
            "default_profile": self.default_profile_id,
            "profiles": {
                definition.profile.profile_id: definition.profile.to_mapping()
                for definition in self._definitions.values()
            },
        }


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
