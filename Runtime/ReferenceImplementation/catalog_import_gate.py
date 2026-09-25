"""既存SubAgent Profile Catalog向けのOffline検証とImport Plan生成。

このモジュールは読取専用であり、Hub SnapshotをUnityAgent所有の契約と照合して
レビュー可能なPlanを返す。Runtime Catalogの置換やProject Environmentの観測は行わない。
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path
import re
from typing import Any

import yaml

from Runtime.Tooling.provider_contract import ProviderRegistry, load_provider_registry

from .profiles import CATALOG, ProfileValidationError, SubAgentProfileCatalog


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_REF = "Runtime/ReferenceImplementation/subagent-catalog.yaml"
DEFAULT_CATALOG_PATH = ROOT / DEFAULT_CATALOG_REF
ENVIRONMENT_SCHEMA_PATH = ROOT / "Runtime/Contracts/environment-snapshot.schema.yaml"
PROFILE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*_subagent$")
PROVIDER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
PROTECTED_FIELD_ROOTS = frozenset(
    {
        "profile_id",
        "provider_id",
        "audience",
        "goal_type",
        "capabilities",
        "primary_capability",
        "required_evidence",
        "activation",
        "scope",
        "value",
        "approval",
        "evidence",
    }
)


class CatalogImportError(ValueError):
    """SnapshotがOffline Import境界を安全に通過できない。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
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


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _expected_digest(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise CatalogImportError("invalid_expected_sha256", "expected SHA-256 must be a non-empty string")
    digest = value.removeprefix("sha256:")
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise CatalogImportError("invalid_expected_sha256", "expected SHA-256 must contain 64 lowercase hexadecimal characters")
    return "sha256:" + digest


def _load_snapshot(snapshot_bytes: bytes) -> SubAgentProfileCatalog:
    try:
        text = snapshot_bytes.decode("utf-8")
    except (AttributeError, UnicodeDecodeError) as exc:
        raise CatalogImportError("snapshot_encoding", "snapshot must be valid UTF-8 bytes") from exc
    try:
        raw = yaml.load(text, Loader=_UniqueKeyLoader)
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        raise CatalogImportError("snapshot_syntax", str(exc)) from exc
    try:
        return SubAgentProfileCatalog.from_mapping(raw)
    except (OverflowError, ProfileValidationError, TypeError, ValueError) as exc:
        raise CatalogImportError("profile_validation", str(exc)) from exc


def _resolve_schema_node(schema: Mapping[str, Any], node: Any) -> Any:
    if not isinstance(node, Mapping):
        return node
    reference = node.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        definitions = schema.get("$defs")
        if isinstance(definitions, Mapping):
            return definitions.get(reference.removeprefix("#/$defs/"), node)
    return node


def _environment_fact_paths(schema: Mapping[str, Any]) -> frozenset[str]:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or not isinstance(schema.get("$defs"), Mapping):
        raise CatalogImportError("environment_schema", "Environment Snapshot schema has no resolvable properties")

    paths: set[str] = set()

    def visit(node: Any, prefix: tuple[str, ...]) -> None:
        if not isinstance(node, Mapping):
            return
        node_properties = node.get("properties")
        if not isinstance(node_properties, Mapping):
            return
        for key, child in node_properties.items():
            if not isinstance(key, str):
                continue
            path = prefix + (key,)
            if isinstance(child, Mapping) and child.get("$ref") == "#/$defs/tri_state":
                paths.add(".".join(path))
                continue
            visit(_resolve_schema_node(schema, child), path)

    visit({"properties": properties}, ())
    return frozenset(paths)


def _validate_semantics(catalog: SubAgentProfileCatalog, provider_registry: ProviderRegistry) -> None:
    try:
        environment_schema = yaml.safe_load(ENVIRONMENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CatalogImportError("environment_schema", str(exc)) from exc
    if not isinstance(environment_schema, Mapping):
        raise CatalogImportError("environment_schema", "Environment Snapshot schema root must be a mapping")
    fact_paths = _environment_fact_paths(environment_schema)

    for provider in provider_registry.providers.values():
        for offer in provider.capabilities.values():
            for fact_path, _expected in offer.environment_requirements:
                if fact_path not in fact_paths:
                    raise CatalogImportError(
                        "provider_environment_fact",
                        f"{provider.provider_id}: {fact_path} is not a tri-state Environment Fact in the current schema",
                    )

    seen_providers: dict[str, str] = {}
    seen_goals: dict[str, str] = {}
    seen_capabilities: dict[str, str] = {}
    for definition in catalog.definitions():
        profile = definition.profile
        if PROFILE_ID_PATTERN.fullmatch(profile.profile_id) is None:
            raise CatalogImportError("invalid_identity", f"invalid profile_id: {profile.profile_id!r}")
        if PROVIDER_ID_PATTERN.fullmatch(profile.provider_id) is None:
            raise CatalogImportError("invalid_provider", f"invalid provider_id: {profile.provider_id!r}")
        if profile.profile_id == profile.provider_id:
            raise CatalogImportError("identity_provider_collision", f"{profile.profile_id} must differ from provider_id")
        provider = provider_registry.providers.get(profile.provider_id)
        if provider is None:
            raise CatalogImportError("unknown_provider", f"unknown provider_id: {profile.provider_id}")
        if not provider.production_enabled:
            raise CatalogImportError("provider_disabled", f"provider is production-disabled: {profile.provider_id}")
        if profile.provider_id in seen_providers:
            raise CatalogImportError(
                "duplicate_provider",
                f"provider_id {profile.provider_id} is used by both {seen_providers[profile.provider_id]} and {profile.profile_id}",
            )
        seen_providers[profile.provider_id] = profile.profile_id

        if profile.goal_type in seen_goals:
            raise CatalogImportError(
                "duplicate_goal_type",
                f"goal_type {profile.goal_type} is used by both {seen_goals[profile.goal_type]} and {profile.profile_id}",
            )
        seen_goals[profile.goal_type] = profile.profile_id

        if profile.value and profile.approval:
            value_minimum = float(profile.value["minimum"])
            value_maximum = float(profile.value["maximum"])
            approval_minimum = float(profile.approval["default_minimum"])
            approval_maximum = float(profile.approval["default_maximum"])
            if (
            approval_minimum < value_minimum
            or approval_maximum > value_maximum
            or (profile.approval["minimum_exclusive"] and approval_minimum <= value_minimum)
            or (profile.value["maximum_exclusive"] and approval_maximum >= value_maximum)
            or (profile.approval["maximum_exclusive"] and approval_maximum >= value_maximum)
            ):
                raise CatalogImportError(
                    "approval_outside_value",
                    f"{profile.profile_id}: approval defaults must remain inside the value range",
                )

        for capability in profile.capabilities:
            if CAPABILITY_PATTERN.fullmatch(capability) is None:
                raise CatalogImportError("invalid_capability", f"invalid capability: {capability!r}")
            if capability in seen_capabilities:
                raise CatalogImportError(
                    "duplicate_capability",
                    f"capability {capability} is used by both {seen_capabilities[capability]} and {profile.profile_id}",
                )
            seen_capabilities[capability] = profile.profile_id

        if profile.goal_type not in profile.capabilities:
            raise CatalogImportError(
                "goal_capability_mismatch",
                f"{profile.profile_id}: goal_type {profile.goal_type!r} must be declared in capabilities",
            )

        for fact_path in profile.activation["required_environment"]:
            if fact_path not in fact_paths:
                raise CatalogImportError(
                    "unknown_environment_fact",
                    f"{profile.profile_id}: {fact_path} is not a tri-state Environment Fact in the current schema",
                )


def _diff_paths(before: Any, after: Any, prefix: str = "") -> list[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: list[str] = []
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                paths.append(path)
            else:
                paths.extend(_diff_paths(before[key], after[key], path))
        return paths
    return [] if before == after else [prefix]


def _is_protected(path: str) -> bool:
    root = path.split(".", 1)[0]
    return root in PROTECTED_FIELD_ROOTS


def _change_risk(classification: str, changed_fields: list[str], protected_fields: list[str]) -> str:
    if classification in {"Added", "Removed"} or protected_fields:
        return "high"
    if changed_fields:
        return "low"
    return "none"


def build_import_plan(
    snapshot_bytes: bytes,
    *,
    source_ref: str,
    expected_sha256: str,
    current_catalog: SubAgentProfileCatalog | None = CATALOG,
    current_catalog_bytes: bytes | bytearray | None = None,
    current_catalog_ref: str = DEFAULT_CATALOG_REF,
    current_catalog_sha256: str | None = None,
    provider_registry: ProviderRegistry | None = None,
) -> dict[str, Any]:
    """Offline Snapshotを検証し、Catalogを書き換えないImport Planを返す。"""
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise CatalogImportError("invalid_source_ref", "source_ref must be a non-empty string")
    if not isinstance(snapshot_bytes, (bytes, bytearray)):
        raise CatalogImportError("snapshot_input_type", "snapshot input must be bytes")
    payload = bytes(snapshot_bytes)
    expected = _expected_digest(expected_sha256)
    actual = _sha256(payload)
    if actual != expected:
        raise CatalogImportError(
            "snapshot_digest_mismatch",
            f"expected {expected}, observed {actual}",
        )
    incoming_catalog = _load_snapshot(payload)
    if current_catalog_bytes is None:
        if current_catalog is not CATALOG:
            raise CatalogImportError(
                "current_catalog_source_required",
                "current catalog bytes are required when using a non-canonical catalog object",
            )
        try:
            current_catalog_bytes = DEFAULT_CATALOG_PATH.read_bytes()
        except OSError as exc:
            raise CatalogImportError("current_catalog_source", str(exc)) from exc
    if not isinstance(current_catalog_bytes, (bytes, bytearray)):
        raise CatalogImportError("current_catalog_input_type", "current catalog input must be bytes")
    current_payload = bytes(current_catalog_bytes)
    current_digest = _sha256(current_payload)
    if current_catalog_sha256 is not None and _expected_digest(current_catalog_sha256) != current_digest:
        raise CatalogImportError(
            "current_catalog_digest_mismatch",
            f"expected {_expected_digest(current_catalog_sha256)}, observed {current_digest}",
        )
    try:
        parsed_current_catalog = _load_snapshot(current_payload)
    except CatalogImportError as exc:
        raise CatalogImportError("current_catalog_validation", str(exc)) from exc
    if current_catalog is not None and current_catalog.to_mapping() != parsed_current_catalog.to_mapping():
        raise CatalogImportError(
            "current_catalog_mismatch",
            "current catalog object does not match the exact current catalog bytes",
        )
    current_catalog = parsed_current_catalog
    try:
        registry = provider_registry or load_provider_registry()
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise CatalogImportError("provider_registry", str(exc)) from exc
    _validate_semantics(incoming_catalog, registry)
    _validate_semantics(current_catalog, registry)

    current_profiles = current_catalog.to_mapping()["profiles"]
    incoming_profiles = incoming_catalog.to_mapping()["profiles"]
    changes: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    for profile_id in sorted(set(current_profiles) | set(incoming_profiles)):
        if profile_id not in current_profiles:
            classification = "Added"
            changed_fields: list[str] = []
            protected_fields: list[str] = []
        elif profile_id not in incoming_profiles:
            classification = "Removed"
            changed_fields = []
            protected_fields = []
            blocking_reasons.append(f"removed_profile:{profile_id}")
        else:
            changed_fields = _diff_paths(current_profiles[profile_id], incoming_profiles[profile_id])
            classification = "Changed" if changed_fields else "No-op"
            protected_fields = sorted(path for path in changed_fields if _is_protected(path))
            for path in protected_fields:
                blocking_reasons.append(f"protected_field_changed:{profile_id}:{path}")
        risk = _change_risk(classification, changed_fields, protected_fields)
        changes.append(
            {
                "profile_id": profile_id,
                "classification": classification,
                "changed_fields": changed_fields,
                "protected_fields_changed": protected_fields,
                "risk": risk,
            }
        )

    default_changed = current_catalog.default_profile_id != incoming_catalog.default_profile_id
    if default_changed:
        blocking_reasons.append("default_profile_changed")
    changed = any(item["classification"] != "No-op" for item in changes) or default_changed
    if blocking_reasons:
        status = "blocked"
        plan_risk = "high"
    elif changed:
        status = "requires_pull_request"
        plan_risk = "high" if any(item["risk"] == "high" for item in changes) else "low"
    else:
        status = "no_op"
        plan_risk = "none"
    return {
        "kind": "subagent_catalog_import_plan",
        "schema_version": "1.0",
        "status": status,
        "risk": plan_risk,
        "source": {"ref": source_ref, "sha256": actual},
        "current_catalog": {"ref": current_catalog_ref, "sha256": current_digest},
        "catalog": {
            "current_default_profile": current_catalog.default_profile_id,
            "incoming_default_profile": incoming_catalog.default_profile_id,
            "default_profile_changed": default_changed,
        },
        "validation": {
            "syntax": "passed",
            "strict_schema": "passed",
            "semantic": "passed",
        },
        "changes": changes,
        "blocking_reasons": sorted(blocking_reasons),
        "apply": {
            "mode": "read_only",
            "catalog_write_performed": False,
            "requires_pull_request": changed,
            "apply_allowed": False,
        },
    }
