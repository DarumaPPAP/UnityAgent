"""Hub SnapshotのOffline検証とUnityAgent Catalog Import Plan生成。

このモジュールは読取専用であり、静的Hub SnapshotをUnityAgent所有の契約へ適合させて
レビュー可能なPlanを返す。Runtime Catalogの置換やProject Environmentの観測は行わない。
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator
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


HUB_MANIFEST_KEYS = frozenset({"schema_version", "kind", "identity", "lifecycle", "installation", "activation", "capabilities", "capability_contract_ref", "compatibility", "dependencies", "backends", "evidence"})
HUB_MANIFEST_REF = re.compile(r"^SubAgents/([a-z][a-z0-9_]*_subagent)/manifest\.yaml$")
HUB_SNAPSHOT_SCHEMA_PATH = ROOT / "Runtime/ReferenceImplementation/Schemas/hub-snapshot-v1.schema.json"
HUB_MANIFEST_SCHEMA_PATH = ROOT / "Runtime/ReferenceImplementation/Schemas/hub-manifest-v3.schema.json"


def _validate_hub_schema(snapshot: Mapping[str, Any]) -> None:
    """Validate pinned Hub contracts before adapting their runtime-relevant fields."""
    try:
        snapshot_schema = json.loads(HUB_SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
        manifest_schema = json.loads(HUB_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogImportError("hub_schema_unavailable", str(exc)) from exc
    errors = list(Draft202012Validator(snapshot_schema).iter_errors(snapshot))
    if errors:
        raise CatalogImportError("hub_snapshot_schema", f"snapshot: {errors[0].message}")
    for index, entry in enumerate(snapshot["specialists"]):
        errors = list(Draft202012Validator(manifest_schema).iter_errors(entry["manifest"]))
        if errors:
            raise CatalogImportError("hub_snapshot_schema", f"specialists[{index}].manifest: {errors[0].message}")


def _exact_mapping(value: Any, expected: frozenset[str], location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise CatalogImportError("hub_snapshot_schema", f"{location} must contain exactly {sorted(expected)}")
    return value


def _hub_profile_catalog(snapshot: Mapping[str, Any], consumer_catalog: SubAgentProfileCatalog) -> SubAgentProfileCatalog:
    _exact_mapping(snapshot, frozenset({"schema_version", "kind", "specialists"}), "Hub snapshot")
    if snapshot["schema_version"] != "1.0" or snapshot["kind"] != "subagent_catalog_snapshot":
        raise CatalogImportError("hub_snapshot_schema", "unsupported Hub snapshot version or kind")
    specialists = snapshot["specialists"]
    if not isinstance(specialists, list) or not specialists:
        raise CatalogImportError("hub_snapshot_schema", "specialists must be a non-empty list")

    profiles: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for index, entry in enumerate(specialists):
        entry = _exact_mapping(entry, frozenset({"manifest_ref", "manifest"}), f"specialists[{index}]")
        reference = entry["manifest_ref"]
        match = HUB_MANIFEST_REF.fullmatch(reference) if isinstance(reference, str) else None
        if match is None:
            raise CatalogImportError("hub_snapshot_schema", f"specialists[{index}].manifest_ref is invalid")
        manifest = _exact_mapping(entry["manifest"], HUB_MANIFEST_KEYS, f"specialists[{index}].manifest")
        if manifest["schema_version"] != "3.0" or manifest["kind"] != "subagent_manifest":
            raise CatalogImportError("hub_snapshot_schema", f"specialists[{index}] requires Manifest v3")
        identity = _exact_mapping(manifest["identity"], frozenset({"id", "name", "version"}), f"specialists[{index}].identity")
        profile_id = identity["id"]
        if not isinstance(profile_id, str) or profile_id != match.group(1) or profile_id in seen_ids or not isinstance(identity["name"], str) or not identity["name"] or not isinstance(identity["version"], str) or not identity["version"]:
            raise CatalogImportError("hub_snapshot_schema", f"specialists[{index}] has a mismatched or duplicate identity")
        seen_ids.add(profile_id)
        if not isinstance(manifest["lifecycle"], str) or manifest["lifecycle"] not in {"active", "deprecated", "retired", "revoked"}:
            raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid lifecycle")
        if not isinstance(manifest["capability_contract_ref"], str) or not manifest["capability_contract_ref"]:
            raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid capability contract reference")
        compatibility = _exact_mapping(manifest["compatibility"], frozenset({"supported_targets", "support_matrix_ref"}), f"{profile_id}.compatibility")
        targets = compatibility["supported_targets"]
        if not isinstance(targets, list) or not targets or not isinstance(compatibility["support_matrix_ref"], str) or not compatibility["support_matrix_ref"]:
            raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid compatibility")
        for target in targets:
            target = _exact_mapping(target, frozenset({"unity_version", "render_pipeline"}), f"{profile_id}.supported_target")
            if any(not isinstance(value, str) or not value for value in target.values()):
                raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid supported target")
        if manifest["lifecycle"] != "active":
            continue

        try:
            current = consumer_catalog.get(profile_id)
        except ProfileValidationError as exc:
            raise CatalogImportError("consumer_profile_required", f"{profile_id}: UnityAgent must define consumer-owned Profile fields before import") from exc
        installation = _exact_mapping(manifest["installation"], frozenset({"mode", "required", "auto_install"}), f"{profile_id}.installation")
        activation = _exact_mapping(manifest["activation"], frozenset({"required_before_resolution", "false_behavior", "unknown_behavior"}), f"{profile_id}.activation")
        if installation != {"mode": "optional", "required": False, "auto_install": False} or activation["false_behavior"] != "exclude_from_resolution" or activation["unknown_behavior"] != "exclude_from_resolution":
            raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: activation must remain optional and fail closed")
        required_environment = activation["required_before_resolution"]
        if not isinstance(required_environment, list) or not required_environment or any(not isinstance(item, str) or not item for item in required_environment) or len(set(required_environment)) != len(required_environment):
            raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid activation facts")

        backend_ids: set[str] = set()
        backends = manifest["backends"]
        if not isinstance(backends, list) or not backends:
            raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: backends must be non-empty")
        for backend in backends:
            if not isinstance(backend, Mapping) or not set(backend).issubset({"id", "kind", "executable", "package_id", "transport", "contract_ref"}) or not {"id", "kind", "contract_ref"}.issubset(backend):
                raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid backend")
            if not isinstance(backend["id"], str) or PROVIDER_ID_PATTERN.fullmatch(backend["id"]) is None or any(not isinstance(backend[key], str) or not backend[key] for key in backend):
                raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid backend identity or reference")
            backend_ids.add(backend["id"])
        if len(backend_ids) != len(backends) or current.provider_id not in backend_ids:
            raise CatalogImportError("provider_binding_required", f"{profile_id}: current UnityAgent provider is not declared by Hub backends")
        dependencies = manifest["dependencies"]
        if not isinstance(dependencies, list) or any(not isinstance(item, Mapping) or not set(item).issubset({"id", "kind", "required", "eligibility_gate"}) or not {"id", "kind", "required"}.issubset(item) or not isinstance(item["id"], str) or not isinstance(item["kind"], str) or not isinstance(item["required"], bool) for item in dependencies):
            raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid dependencies")
        if not any(item.get("id") == current.provider_id and item.get("kind") == "backend" and item.get("required") is True and item.get("eligibility_gate") in required_environment for item in dependencies):
            raise CatalogImportError("provider_binding_required", f"{profile_id}: current provider has no required activation gate")

        capabilities = manifest["capabilities"]
        if not isinstance(capabilities, list) or not capabilities:
            raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: capabilities must be non-empty")
        flattened: list[str] = []
        for capability in capabilities:
            capability = _exact_mapping(capability, frozenset({"id", "operations"}), f"{profile_id}.capability")
            if not isinstance(capability["id"], str) or not isinstance(capability["operations"], list) or not capability["operations"] or any(not isinstance(operation, str) or not operation for operation in capability["operations"]):
                raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid capability")
            flattened.extend(f"{capability['id']}.{operation}" for operation in capability["operations"])
        evidence = _exact_mapping(manifest["evidence"], frozenset({"required", "required_artifacts", "runtime_types", "terminal_states", "contract_ref"}), f"{profile_id}.evidence")
        if evidence["required"] is not True or any(not isinstance(evidence[key], list) or not evidence[key] or any(not isinstance(item, str) or not item for item in evidence[key]) for key in ("required_artifacts", "runtime_types", "terminal_states")) or not isinstance(evidence["contract_ref"], str) or not evidence["contract_ref"]:
            raise CatalogImportError("hub_snapshot_schema", f"{profile_id}: invalid evidence requirements")
        profile = current.to_mapping()
        profile.update(display_name=identity["name"], capabilities=flattened, required_evidence=evidence["runtime_types"], activation={"install_mode": installation["mode"], "auto_install": installation["auto_install"], "required_environment": required_environment})
        profiles[profile_id] = profile

    if not profiles:
        raise CatalogImportError("hub_snapshot_schema", "Hub snapshot has no active specialists")
    return SubAgentProfileCatalog.from_mapping({"schema_version": consumer_catalog.schema_version, "default_profile": consumer_catalog.default_profile_id, "profiles": profiles})


def _load_snapshot(snapshot_bytes: bytes, *, consumer_catalog: SubAgentProfileCatalog | None = None) -> SubAgentProfileCatalog:
    try:
        text = snapshot_bytes.decode("utf-8")
    except (AttributeError, UnicodeDecodeError) as exc:
        raise CatalogImportError("snapshot_encoding", "snapshot must be valid UTF-8 bytes") from exc
    try:
        raw = yaml.load(text, Loader=_UniqueKeyLoader)
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        raise CatalogImportError("snapshot_syntax", str(exc)) from exc
    try:
        if isinstance(raw, Mapping) and raw.get("kind") == "subagent_catalog_snapshot":
            if consumer_catalog is None:
                raise CatalogImportError("consumer_catalog_required", "Hub snapshot import requires a UnityAgent-owned Catalog")
            _validate_hub_schema(raw)
            return _hub_profile_catalog(raw, consumer_catalog)
        return SubAgentProfileCatalog.from_mapping(raw)
    except CatalogImportError:
        raise
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
    incoming_catalog = _load_snapshot(payload, consumer_catalog=current_catalog)
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
