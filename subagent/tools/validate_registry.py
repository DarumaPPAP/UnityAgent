#!/usr/bin/env python3
"""Validate the SubAgent Hub registry and every indexed SubAgent manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = "subagent/registry.yaml"
REGISTRY_SCHEMA_PATH = "subagent/schemas/subagent-registry.schema.json"
MANIFEST_SCHEMA_PATH = "subagent/schemas/subagent-manifest.schema.json"
MANIFEST_ROOT = "subagent"
LIFECYCLES = {"active", "deprecated", "retired", "revoked"}
SUBAGENT_ID = re.compile(r"^[a-z][a-z0-9_]*_subagent$")
BACKEND_ID = re.compile(r"^[a-z][a-z0-9_]*$")
MANIFEST_PATH = re.compile(r"^subagent/([a-z][a-z0-9_]*_subagent)/manifest\.yaml$")
SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema", "$id", "title", "description", "type", "additionalProperties", "required", "properties",
    "const", "enum", "minItems", "maxItems", "oneOf", "uniqueItems", "items", "pattern", "minLength", "minimum",
}


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject ambiguous YAML mappings at the canonical contract boundary."""


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate YAML key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _read_yaml(path: Path, errors: list[str]) -> Any:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except FileNotFoundError:
        errors.append(f"missing YAML file: {path}")
    except (OSError, yaml.YAMLError) as exc:
        errors.append(f"invalid YAML file {path}: {exc}")
    return None


def _read_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing JSON Schema: {path}")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON Schema {path}: {exc}")
    return None


def _check_schema_definition(schema: Any, location: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        errors.append(f"{location}: schema root must be an object")
        return {}
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append(f"{location}: schema must declare JSON Schema Draft 2020-12")
    if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
        errors.append(f"{location}: schema must define an object with properties")
    if not isinstance(schema.get("required"), list):
        errors.append(f"{location}: schema must declare required properties")
    return schema


def _schema_errors(value: Any, schema: Any, location: str, errors: list[str]) -> None:
    """Apply the constrained JSON Schema subset used by the checked-in contracts."""
    if not isinstance(schema, dict):
        errors.append(f"{location}: schema node must be an object")
        return
    unsupported = sorted(set(schema) - SUPPORTED_SCHEMA_KEYWORDS)
    if unsupported:
        errors.append(f"{location}: schema uses unsupported keywords {unsupported}; extend the validator before relying on them")
    additional_properties = schema.get("additionalProperties")
    if additional_properties is not None and not isinstance(additional_properties, bool):
        errors.append(f"{location}: additionalProperties must be boolean")

    if "oneOf" in schema:
        alternatives = schema["oneOf"]
        if not isinstance(alternatives, list) or not alternatives:
            errors.append(f"{location}: oneOf must contain schemas")
        else:
            matches = 0
            for alternative in alternatives:
                branch_errors: list[str] = []
                _schema_errors(value, alternative, location, branch_errors)
                matches += not branch_errors
            if matches != 1:
                errors.append(f"{location}: exactly one execution contract must match (matched {matches})")

    type_name = schema.get("type")
    type_checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
    }
    if type_name is not None and (not isinstance(type_name, str) or type_name not in type_checks):
        errors.append(f"{location}: unsupported schema type {type_name!r}")
        return
    if type_name in type_checks and not type_checks[type_name](value):
        errors.append(f"{location}: expected {type_name}")
        return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: must be one of {schema['enum']!r}")
    if "minimum" in schema and isinstance(value, (int, float)) and not isinstance(value, bool) and value < schema["minimum"]:
        errors.append(f"{location}: must be at least {schema['minimum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{location}: must not be empty")
        pattern = schema.get("pattern")
        if pattern and re.fullmatch(pattern, value) is None:
            errors.append(f"{location}: does not match required pattern {pattern!r}")
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{location}: must contain at most {schema['maxItems']} item(s)")
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{location}: must contain at least {schema['minItems']} item(s)")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True, default=str) for item in value}) != len(value):
            errors.append(f"{location}: items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _schema_errors(item, item_schema, f"{location}[{index}]", errors)
    if isinstance(value, dict):
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{location}: missing required property {required!r}")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                _schema_errors(item, properties[key], f"{location}.{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{location}: unexpected property {key!r}")


def _valid_reference(root: Path, value: Any, location: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{location}: contract reference must be a non-empty repository-relative path")
        return
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        errors.append(f"{location}: contract reference must not escape the repository: {value!r}")
        return
    resolved = (root / Path(*path.parts)).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        errors.append(f"{location}: contract reference resolves outside the repository: {value!r}")
        return
    if not resolved.is_file():
        errors.append(f"{location}: referenced contract file does not exist: {value}")


def _validate_registry(root: Path, schema: Any, errors: list[str]) -> tuple[dict[str, Any], list[str]]:
    path = root / REGISTRY_PATH
    registry = _read_yaml(path, errors)
    if not isinstance(registry, dict):
        errors.append("subagent/registry.yaml: root must be a mapping")
        return {}, []
    _schema_errors(registry, schema, REGISTRY_PATH, errors)

    if registry.get("schema_version") != "2.0" or registry.get("kind") != "subagent_registry":
        errors.append("subagent/registry.yaml: unsupported schema_version or kind")

    entries = registry.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("subagent/registry.yaml: entries must list at least one manifest")
        entries = []
    paths: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("manifest"), str):
            errors.append(f"subagent/registry.yaml: entries[{index}] must contain a manifest path")
            continue
        manifest_path = entry["manifest"]
        if not MANIFEST_PATH.fullmatch(manifest_path):
            errors.append(f"subagent/registry.yaml: invalid manifest path {manifest_path!r}")
            continue
        paths.append(manifest_path)
    if len(set(paths)) != len(paths):
        errors.append("subagent/registry.yaml: manifest entries must be unique")
    return registry, paths


def _validate_manifest(root: Path, path: str, schema: Any, errors: list[str]) -> dict[str, Any] | None:
    manifest_file = root / Path(*PurePosixPath(path).parts)
    try:
        manifest_file.resolve().relative_to(root.resolve())
    except ValueError:
        errors.append(f"{path}: manifest resolves outside the repository")
        return None
    manifest = _read_yaml(manifest_file, errors)
    if not isinstance(manifest, dict):
        errors.append(f"{path}: root must be a mapping")
        return None
    _schema_errors(manifest, schema, path, errors)

    identity = manifest.get("identity") if isinstance(manifest.get("identity"), dict) else {}
    subagent_id = identity.get("id")
    match = MANIFEST_PATH.fullmatch(path)
    if not isinstance(subagent_id, str) or not SUBAGENT_ID.fullmatch(subagent_id):
        errors.append(f"{path}: identity.id must be a canonical *_subagent id")
    elif match and subagent_id != match.group(1):
        errors.append(f"{path}: identity.id must match its subagent/<id> directory")

    if manifest.get("lifecycle") not in LIFECYCLES:
        errors.append(f"{path}: lifecycle must be active, deprecated, retired, or revoked")
    installation = manifest.get("installation")
    if not isinstance(installation, dict) or installation.get("mode") != "optional":
        errors.append(f"{path}: every SubAgent must be optional")
    if not isinstance(installation, dict) or installation.get("required") is not False:
        errors.append(f"{path}: specialist installation must remain optional")
    if not isinstance(installation, dict) or installation.get("auto_install") is not False:
        errors.append(f"{path}: SubAgents must not auto-install")

    activation = manifest.get("activation")
    if not isinstance(activation, dict):
        activation = {}
    gates = activation.get("required_before_resolution")
    if not isinstance(gates, list) or not gates or any(not isinstance(gate, str) or not gate for gate in gates):
        errors.append(f"{path}: activation.required_before_resolution must list required environment checks")
    if activation.get("false_behavior") != "exclude_from_resolution" or activation.get("unknown_behavior") != "exclude_from_resolution":
        errors.append(f"{path}: false and unknown activation checks must exclude the SubAgent")

    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        capabilities = []
        # The schema reports the structural failure; continue with reference checks.
    capability_ids: list[str] = []
    for index, capability in enumerate(capabilities):
        if not isinstance(capability, dict):
            continue
        capability_id = capability.get("id")
        operations = capability.get("operations")
        if not isinstance(capability_id, str) or not capability_id or not isinstance(operations, list) or not operations:
            errors.append(f"{path}: capabilities[{index}] requires an id and supported operations")
        if isinstance(capability_id, str):
            capability_ids.append(capability_id)
    if len(set(capability_ids)) != len(capability_ids):
        errors.append(f"{path}: capability ids must be unique")
    _valid_reference(root, manifest.get("capability_contract_ref"), f"{path}: capability_contract_ref", errors)

    execution = manifest.get("execution")
    if isinstance(execution, dict) and execution.get("kind") == "reasoning":
        for field in ("instructions_ref", "output_contract_ref"):
            _valid_reference(root, execution.get(field), f"{path}: execution.{field}", errors)
        semantic = {f"{item['id']}.{operation}" for item in capabilities if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("operations"), list) for operation in item["operations"] if isinstance(operation, str)}
        observations = execution.get("required_observation_capabilities")
        if isinstance(observations, list) and any(isinstance(item, str) and item in semantic for item in observations):
            errors.append(f"{path}: semantic reasoning capabilities cannot be observation Tool capabilities")

    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict):
        errors.append(f"{path}: compatibility contract is required")

    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, list):
        dependencies = []
    dependency_ids: set[str] = set()
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict):
            continue
        dependency_id = dependency.get("id")
        if not isinstance(dependency_id, str) or not dependency_id:
            errors.append(f"{path}: dependencies[{index}].id is required")
        elif dependency_id in dependency_ids:
            errors.append(f"{path}: dependency ids must be unique")
        else:
            dependency_ids.add(dependency_id)
        gate = dependency.get("eligibility_gate")
        if dependency.get("required") is True:
            if not isinstance(gate, str) or not gate:
                errors.append(f"{path}: dependencies[{index}].eligibility_gate is required for required dependencies")
            elif isinstance(gates, list) and gate not in gates:
                errors.append(f"{path}: required dependency gate {gate!r} must be checked before resolution")

    backends = manifest.get("backends")
    if not isinstance(backends, list) or not backends:
        backends = []
        # The schema reports the structural failure.
    backend_ids: list[str] = []
    for index, backend in enumerate(backends):
        if not isinstance(backend, dict):
            continue
        backend_id = backend.get("id")
        if not isinstance(backend_id, str) or not BACKEND_ID.fullmatch(backend_id):
            errors.append(f"{path}: backends[{index}].id must be a valid backend id")
            continue
        backend_ids.append(backend_id)
        if backend_id == subagent_id:
            errors.append(f"{path}: backend identity must differ from SubAgent identity")
        _valid_reference(root, backend.get("contract_ref"), f"{path}: backends[{index}].contract_ref", errors)
    if len(set(backend_ids)) != len(backend_ids):
        errors.append(f"{path}: backend ids must be unique within a manifest")
    declared_backend_ids = set(backend_ids)
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict) or dependency.get("kind") != "backend":
            continue
        dependency_id = dependency.get("id")
        if dependency_id not in declared_backend_ids:
            errors.append(f"{path}: backend dependency {dependency_id!r} must reference a backend declared in backends")
    evidence = manifest.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("required") is not True:
        errors.append(f"{path}: evidence must be required")
    else:
        runtime_types = evidence.get("runtime_types")
        if not isinstance(runtime_types, list) or not runtime_types or any(not isinstance(value, str) or not value for value in runtime_types):
            errors.append(f"{path}: evidence.runtime_types must list UnityAgent evidence types")
    return manifest


def validate_repository(root: Path = ROOT) -> list[str]:
    """Return every Hub contract violation found in the repository tree."""
    errors: list[str] = []
    manifest_schema = _check_schema_definition(_read_json(root / MANIFEST_SCHEMA_PATH, errors), MANIFEST_SCHEMA_PATH, errors)
    registry_schema = _check_schema_definition(_read_json(root / REGISTRY_SCHEMA_PATH, errors), REGISTRY_SCHEMA_PATH, errors)
    _, registered_paths = _validate_registry(root, registry_schema, errors)
    manifest_root = root / MANIFEST_ROOT
    discovered_paths = sorted(
        path.relative_to(root).as_posix()
        for path in manifest_root.rglob("manifest.yaml")
    ) if manifest_root.is_dir() else []
    if not manifest_root.is_dir():
        errors.append("subagent/: directory is required")
    if set(registered_paths) != set(discovered_paths):
        errors.append("subagent/registry.yaml: registry entries do not cover all manifests exactly once")
    for path in registered_paths:
        _validate_manifest(root, path, manifest_schema, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT, help="repository root to validate")
    args = parser.parse_args(argv)
    errors = validate_repository(args.repo_root.resolve())
    if errors:
        for message in errors:
            print(f"[ERROR] {message}")
        print(f"SubAgent Hub contract: {len(errors)} error(s)")
        return 1
    print("SubAgent Hub contract: 0 error(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
