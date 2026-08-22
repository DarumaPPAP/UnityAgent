#!/usr/bin/env python3
"""Validate Context Pack execution contracts and exploration metadata."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml


PACK_DIR = Path(".ai/context-packs")
INDEX_PATH = Path(".ai/context-index.yaml")
SCHEMA_PATH = Path(".ai/context-pack.schema.yaml")
PROJECT_PROFILE_PATH = "Specs/ProjectProfile.md"
PROJECT_FALLBACK_KEY = "project_fallback"
REQUIRED_PACKS = {
    "architecture-design.yaml",
    "graphics-mcp.yaml",
    "csharp-local-fix.yaml",
    "rendering-incident.yaml",
    "shader-change.yaml",
    "renderer-feature-change.yaml",
    "performance.yaml",
    "asset-data-change.yaml",
    "portable-feature.yaml",
    "visual-direction.yaml",
}
LOCAL_PATH_PREFIXES = (".ai/", ".agents/", "SkillReferences/", "Specs/", "Tools/")
RELATIONS = {"related-to", "depends-on", "hands-off-to", "conflicts-with", "refines"}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_yaml(root: Path, relative: Path | str) -> Any:
    return yaml.safe_load((root / relative).read_text(encoding="utf-8")) or {}


def resolve_source_ref(root: Path, source_ref: str) -> str | None:
    source_path, separator, fragment = source_ref.partition("#")
    if not source_path.startswith(LOCAL_PATH_PREFIXES):
        return "source_ref must use an allowed repository-relative root"
    target = (root / source_path).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        return "source_ref escapes repository root"
    if not target.is_file():
        return f"source file does not exist: {source_path}"
    if not separator or not fragment:
        return None
    try:
        value: Any = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        for key in fragment.split("."):
            if not isinstance(value, dict) or key not in value:
                return f"source fragment does not exist: {source_ref}"
            value = value[key]
    except yaml.YAMLError as exc:
        return f"source fragment cannot be parsed: {source_ref}: {exc}"
    return None


def validate_metadata(root: Path, path: Path, document: dict[str, Any], context_ids: set[str]) -> list[str]:
    errors: list[str] = []
    relative = str(path.relative_to(root)).replace("\\", "/")
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
    tags = metadata.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 8 or not all(isinstance(tag, str) for tag in tags):
        errors.append(f"{relative} metadata.tags must contain at most 8 strings")
    if metadata.get("priority") not in {"critical", "high", "normal", "low"}:
        errors.append(f"{relative} metadata.priority is invalid")

    for field in ("decisions", "forbidden"):
        ids: set[str] = set()
        for item in metadata.get(field, []) or []:
            if not isinstance(item, dict):
                errors.append(f"{relative} metadata.{field} entries must be mappings")
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or not ID_PATTERN.fullmatch(item_id):
                errors.append(f"{relative} metadata.{field} has invalid id: {item_id}")
            if item_id in ids:
                errors.append(f"{relative} metadata.{field} has duplicate id: {item_id}")
            ids.add(item_id)
            if not isinstance(item.get("label"), str) or not item.get("label", "").strip():
                errors.append(f"{relative} metadata.{field}.{item_id} requires label")
            source_ref = item.get("source_ref")
            if not isinstance(source_ref, str):
                errors.append(f"{relative} metadata.{field}.{item_id} requires source_ref")
            else:
                problem = resolve_source_ref(root, source_ref)
                if problem:
                    errors.append(f"{relative} metadata.{field}.{item_id}: {problem}")

    related = metadata.get("related", [])
    if not isinstance(related, list) or len(related) > 8:
        errors.append(f"{relative} metadata.related must contain at most 8 items")
    else:
        for item in related:
            if not isinstance(item, dict):
                errors.append(f"{relative} metadata.related entries must be mappings")
                continue
            target_id = item.get("id")
            if target_id not in context_ids:
                errors.append(f"{relative} metadata.related references unknown context: {target_id}")
            if item.get("relation") not in RELATIONS:
                errors.append(f"{relative} metadata.related has invalid relation: {item.get('relation')}")
            if not isinstance(item.get("reason"), str) or not item.get("reason", "").strip():
                errors.append(f"{relative} metadata.related requires reason")
            source_ref = item.get("source_ref")
            if not isinstance(source_ref, str):
                errors.append(f"{relative} metadata.related requires source_ref")
            else:
                problem = resolve_source_ref(root, source_ref)
                if problem:
                    errors.append(f"{relative} metadata.related: {problem}")
    return errors


def validate_project_profile_fallback(path: Path, document: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    relative = str(path.relative_to(root)).replace("\\", "/")
    required = document.get("required", []) or []
    if PROJECT_PROFILE_PATH in required:
        errors.append(
            f"{relative} must not require {PROJECT_PROFILE_PATH}; it is fallback-only context"
        )

    conditional = document.get("conditional", {}) or {}
    profile_conditions: list[str] = []
    if isinstance(conditional, dict):
        for condition, references in conditional.items():
            if isinstance(references, list) and PROJECT_PROFILE_PATH in references:
                profile_conditions.append(str(condition))

    for condition in profile_conditions:
        if condition != PROJECT_FALLBACK_KEY:
            errors.append(
                f"{relative} may load {PROJECT_PROFILE_PATH} only from conditional.{PROJECT_FALLBACK_KEY}, not conditional.{condition}"
            )

    if profile_conditions:
        rules = document.get("rules", {}) or {}
        if rules.get("project_profile_is_fallback_only") is not True:
            errors.append(f"{relative} must declare rules.project_profile_is_fallback_only: true")

    return errors


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    index_path = root / INDEX_PATH
    pack_dir = root / PACK_DIR
    if not index_path.is_file():
        return [f"Missing file: {INDEX_PATH}"]
    if not (root / SCHEMA_PATH).is_file():
        errors.append(f"Missing file: {SCHEMA_PATH}")

    index = load_yaml(root, INDEX_PATH)
    index_text = index_path.read_text(encoding="utf-8")
    for contract in (
        "user_policy: .ai/user-policy.yaml",
        "user_policy_must_be_loaded_before_domain_decision: true",
        "select_exactly_one_primary_route: true",
        "load_all_skills: false",
        "load_all_references: false",
        "detected_project_facts_override_project_profile: true",
        "user_confirmed_project_facts_override_project_profile: true",
        "project_profile_is_fallback_only: true",
        "project_profile_must_not_be_required_context: true",
        "project_profile_load_requires_missing_project_fact: true",
        "direct_source_read_required_before_mutation: true",
        "do_not_use_legacy_routing_document: true",
    ):
        if contract not in index_text:
            errors.append(f"Missing index contract: {contract}")

    existing_packs = {path.name for path in pack_dir.glob("*.yaml")}
    for pack in sorted(REQUIRED_PACKS - existing_packs):
        errors.append(f"Missing context pack: {pack}")
    documents: dict[str, dict[str, Any]] = {}
    for pack_path in sorted(pack_dir.glob("*.yaml")):
        try:
            documents[pack_path.name] = load_yaml(root, pack_path)
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"{pack_path}: {exc}")
    context_ids = {str(document.get("id")) for document in documents.values() if document.get("id")}
    if len(context_ids) != len(documents):
        errors.append("Context Pack ids must be unique")

    for pack_path, document in ((pack_dir / name, data) for name, data in documents.items()):
        relative = str(pack_path.relative_to(root)).replace("\\", "/")
        for section in ("required", "conditional", "excluded_by_default", "limits", "output"):
            if section not in document:
                errors.append(f"{relative} missing section: {section}")
        if document.get("limits", {}).get("context_expansion_hops") != 1:
            errors.append(f"{relative} must limit context expansion to one hop")
        primary_skill = document.get("primary_skill")
        if not isinstance(primary_skill, str) or not (root / primary_skill).is_file():
            errors.append(f"{relative} has broken primary_skill: {primary_skill}")
        errors.extend(validate_metadata(root, pack_path, document, context_ids))
        errors.extend(validate_project_profile_fallback(pack_path, document, root))

    for route_key, route in (index.get("routes", {}) or {}).items():
        for field in ("context_pack", "task_contract", "primary_skill"):
            value = route.get(field)
            if field == "primary_skill" and isinstance(value, str):
                valid = (root / ".agents" / "skills" / value / "SKILL.md").is_file()
            else:
                valid = isinstance(value, str) and (root / value).is_file()
            if not valid:
                errors.append(f"Route {route_key} has broken {field}: {value}")

    if not (root / ".ai/knowledge-graph-pilot.yaml").is_file():
        errors.append("Missing Knowledge Graph pilot contract.")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate(root)
    if errors:
        print("Context Pack validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Context Pack validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
