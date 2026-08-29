#!/usr/bin/env python3
"""Validate canonical Context Pack v3 contracts after the Phase 8 cutover."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

PACK_DIR = Path("Context/Packs")
INDEX_PATH = Path("Context/Selection/context-catalog.yaml")
SCHEMA_PATH = Path("Context/Contracts/context-pack.schema.yaml")
CONTEXT_PACK_SCHEMA_VERSION = "3.0"
PROJECT_PROFILE_PATH = "Specs/ProjectProfile.md"
PROJECT_FALLBACK_KEY = "project_fallback"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CONTEXT_TYPES = {"binding", "repository_reference", "external_reference", "context_include", "route_handoff"}
LOCAL_PATH_PREFIXES = (
    ".agents/", "Policy/", "Context/", "Orchestration/", "Runtime/",
    "Persistence/", "Operations/", "Eval/", "SkillReferences/", "Specs/", "Tools/",
)
TOP_LEVEL_LOCAL_FILES = {"AGENTS.md", "README.md"}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return data


def canonical_local_path(root: Path, value: str) -> Path:
    text = str(value or "").strip().replace("\\", "/")
    legacy_root = "." + "ai"
    compatibility_scheme = "compatibility" + "://"
    if not text or text.startswith(compatibility_scheme) or text == legacy_root or text.startswith(legacy_root + "/"):
        raise ValueError(f"legacy/non-canonical repository reference: {value}")
    source = text.split("#", 1)[0]
    if not (source.startswith(LOCAL_PATH_PREFIXES) or source in TOP_LEVEL_LOCAL_FILES):
        raise ValueError(f"repository reference uses an unsupported root: {source}")
    target = (root / source).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ValueError(f"repository reference escapes root: {source}")
    if not target.is_file():
        raise ValueError(f"repository reference does not exist: {source}")
    return target


def validate_source_ref(root: Path, source_ref: str) -> str | None:
    try:
        target = canonical_local_path(root, source_ref)
    except ValueError as exc:
        return str(exc)
    _, separator, fragment = source_ref.partition("#")
    if not separator or not fragment or target.suffix.lower() not in {".yaml", ".yml"}:
        return None
    try:
        value: Any = load_yaml(target)
        for key in fragment.split("."):
            if not isinstance(value, dict) or key not in value:
                return f"source fragment does not exist: {source_ref}"
            value = value[key]
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        return f"source fragment cannot be parsed: {source_ref}: {exc}"
    return None


def validate_metadata(root: Path, path: Path, document: dict[str, Any]) -> list[str]:
    relative = path.relative_to(root).as_posix()
    errors: list[str] = []
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        return [f"{relative} missing metadata mapping"]
    if metadata.get("type") != "context":
        errors.append(f"{relative} metadata.type must be context")
    title = metadata.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 80:
        errors.append(f"{relative} metadata.title must be a non-empty string <= 80 characters")
    for field, minimum, maximum in (("summary", 1, 3), ("purpose", 1, 5), ("decisions", 1, 12), ("forbidden", 1, 12)):
        value = metadata.get(field)
        if not isinstance(value, list) or not minimum <= len(value) <= maximum:
            errors.append(f"{relative} metadata.{field} must contain {minimum}..{maximum} items")
    for field in ("decisions", "forbidden"):
        seen: set[str] = set()
        for item in metadata.get(field, []) or []:
            if not isinstance(item, dict):
                errors.append(f"{relative} metadata.{field} entries must be mappings")
                continue
            item_id = str(item.get("id") or "")
            if not ID_PATTERN.fullmatch(item_id):
                errors.append(f"{relative} metadata.{field} has invalid id: {item_id}")
            if item_id in seen:
                errors.append(f"{relative} metadata.{field} has duplicate id: {item_id}")
            seen.add(item_id)
            if not str(item.get("label") or "").strip():
                errors.append(f"{relative} metadata.{field}.{item_id} requires label")
            source_ref = item.get("source_ref")
            if not isinstance(source_ref, str):
                errors.append(f"{relative} metadata.{field}.{item_id} requires source_ref")
            else:
                problem = validate_source_ref(root, source_ref)
                if problem:
                    errors.append(f"{relative} metadata.{field}.{item_id}: {problem}")
    return errors


def validate_typed_item(root: Path, relative: str, section: str, item: Any, context_ids: set[str], route_ids: set[str]) -> list[str]:
    if not isinstance(item, dict):
        return [f"{relative} {section} entries must be typed mappings"]
    errors: list[str] = []
    item_type = item.get("type")
    if item_type not in CONTEXT_TYPES:
        return [f"{relative} {section} has unsupported context type: {item_type}"]
    required_fields = {
        "binding": ("name",),
        "repository_reference": ("path",),
        "external_reference": ("repository", "path"),
        "context_include": ("context_id",),
        "route_handoff": ("route_id",),
    }[str(item_type)]
    for field in required_fields:
        if not str(item.get(field) or "").strip():
            errors.append(f"{relative} {section} {item_type} requires {field}")
    if item_type == "repository_reference" and item.get("path"):
        try:
            canonical_local_path(root, str(item["path"]))
        except ValueError as exc:
            errors.append(f"{relative} {section}: {exc}")
    elif item_type == "external_reference":
        repository = str(item.get("repository") or "")
        if repository and not REPOSITORY_PATTERN.fullmatch(repository):
            errors.append(f"{relative} {section} external repository must use owner/name: {repository}")
        external_path = str(item.get("path") or "")
        if Path(external_path).is_absolute() or ".." in Path(external_path).parts:
            errors.append(f"{relative} {section} external path must be repository-relative: {external_path}")
    elif item_type == "context_include":
        context_id = str(item.get("context_id") or "")
        if context_id and context_id not in context_ids:
            errors.append(f"{relative} {section} includes unknown context: {context_id}")
    elif item_type == "route_handoff":
        route_id = str(item.get("route_id") or "")
        if route_id and route_id not in route_ids:
            errors.append(f"{relative} {section} hands off to unknown route: {route_id}")
    return errors


def validate_pack(root: Path, path: Path, document: dict[str, Any], context_ids: set[str], route_ids: set[str]) -> list[str]:
    relative = path.relative_to(root).as_posix()
    errors: list[str] = []
    if str(document.get("schema_version")) != CONTEXT_PACK_SCHEMA_VERSION:
        errors.append(f"{relative} schema_version must be {CONTEXT_PACK_SCHEMA_VERSION}")
    for section in ("required", "conditional", "excluded_by_default", "limits", "output"):
        if section not in document:
            errors.append(f"{relative} missing section: {section}")
    if (document.get("limits") or {}).get("context_expansion_hops") != 1:
        errors.append(f"{relative} must limit context expansion to one hop")
    primary_skill = document.get("primary_skill")
    if not isinstance(primary_skill, str):
        errors.append(f"{relative} primary_skill is required")
    else:
        try:
            canonical_local_path(root, primary_skill)
        except ValueError as exc:
            errors.append(f"{relative} has broken primary_skill: {exc}")
    errors.extend(validate_metadata(root, path, document))

    required = document.get("required", [])
    if not isinstance(required, list):
        errors.append(f"{relative} required must be a list")
    else:
        for index, item in enumerate(required):
            errors.extend(validate_typed_item(root, relative, f"required[{index}]", item, context_ids, route_ids))

    conditional = document.get("conditional", {})
    if not isinstance(conditional, dict):
        errors.append(f"{relative} conditional must be a mapping")
    else:
        for condition, items in conditional.items():
            if not isinstance(items, list):
                errors.append(f"{relative} conditional.{condition} must be a list")
                continue
            for index, item in enumerate(items):
                errors.extend(validate_typed_item(root, relative, f"conditional.{condition}[{index}]", item, context_ids, route_ids))

    for item in required if isinstance(required, list) else []:
        if isinstance(item, dict) and item.get("type") == "repository_reference" and item.get("path") == PROJECT_PROFILE_PATH:
            errors.append(f"{relative} must not require {PROJECT_PROFILE_PATH}; it is fallback-only context")
    if isinstance(conditional, dict):
        for condition, items in conditional.items():
            for item in items or []:
                if isinstance(item, dict) and item.get("type") == "repository_reference" and item.get("path") == PROJECT_PROFILE_PATH:
                    if condition != PROJECT_FALLBACK_KEY:
                        errors.append(f"{relative} may load {PROJECT_PROFILE_PATH} only from conditional.{PROJECT_FALLBACK_KEY}")
                    if (document.get("rules") or {}).get("project_profile_is_fallback_only") is not True:
                        errors.append(f"{relative} must declare rules.project_profile_is_fallback_only: true")
    return errors


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    index_path = root / INDEX_PATH
    pack_dir = root / PACK_DIR
    schema_path = root / SCHEMA_PATH
    if not index_path.is_file():
        return [f"Missing file: {INDEX_PATH}"]
    if not schema_path.is_file():
        errors.append(f"Missing file: {SCHEMA_PATH}")
    try:
        catalog = load_yaml(index_path)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        return [str(exc)]

    if catalog.get("authority") != "Context":
        errors.append("Context catalog authority must be Context")
    if catalog.get("materializer_requires_explicit_route_id") is not True:
        errors.append("Context catalog must require explicit route_id")
    if catalog.get("user_policy") != "Policy/User/user-policy.yaml":
        errors.append("Context catalog must reference canonical user policy")

    routes = catalog.get("routes") or {}
    if not isinstance(routes, dict) or not routes:
        return errors + ["Context catalog routes must be a non-empty mapping"]
    route_ids = set(str(key) for key in routes)

    documents: dict[str, dict[str, Any]] = {}
    for path in sorted(pack_dir.glob("*.yaml")):
        try:
            documents[path.name] = load_yaml(path)
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
    context_ids = {str(document.get("id")) for document in documents.values() if document.get("id")}
    if len(context_ids) != len(documents):
        errors.append("Context Pack ids must be present and unique")

    for route_id, route in routes.items():
        if not isinstance(route, dict):
            errors.append(f"route {route_id} must be a mapping")
            continue
        for field, prefix in (
            ("context_pack", "Context/Packs/"),
            ("primary_skill", ".agents/skills/"),
            ("task_contract", "Orchestration/Contracts/TaskContracts/"),
        ):
            value = str(route.get(field) or "")
            if not value.startswith(prefix):
                errors.append(f"route {route_id} {field} must use canonical {prefix} root")
                continue
            try:
                canonical_local_path(root, value)
            except ValueError as exc:
                errors.append(f"route {route_id} {field}: {exc}")

    for name, document in documents.items():
        errors.extend(validate_pack(root, pack_dir / name, document, context_ids, route_ids))
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").expanduser().resolve()
    errors = validate(root)
    if errors:
        print("Context Pack validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Context Pack validation passed: canonical catalog, packs, policy, skills and task contracts are coherent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
