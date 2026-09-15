#!/usr/bin/env python3
"""Validate Context Explorer's derived map, offline viewer, and architecture boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from architecture_projection import build_human_architecture  # noqa: E402
from context_map import (  # noqa: E402
    CANONICAL_CONTEXT_PACKS,
    MAP_KIND,
    SCHEMA_VERSION,
    load_context_map,
    validate_context_map,
)


EXPECTED_CONCEPTS = ("rules", "planner", "knowledge", "executor", "evidence", "memory", "quality")


def _validate_schema_contract(root: Path, errors: list[str]) -> None:
    schema_path = root / "Tools/ContextExplorer/schema/context-map.schema.json"
    if not schema_path.is_file():
        errors.append("Context Map schema is missing")
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    required = set(schema.get("required", []))
    if required != {"metadata", "nodes", "edges"}:
        errors.append("Context Map schema must require metadata/nodes/edges")
    metadata_properties = schema.get("properties", {}).get("metadata", {}).get("properties", {})
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": MAP_KIND,
        "generated_from": CANONICAL_CONTEXT_PACKS.as_posix(),
        "generated_by": "ContextExplorer",
        "read_only": True,
    }
    for key, value in expected.items():
        if metadata_properties.get(key, {}).get("const") != value:
            errors.append(f"Context Map schema metadata.{key} drifted from canonical value")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate_context_map(load_context_map(root).to_dict())
    architecture = build_human_architecture(root)

    old_paths = (
        root / "Tools/GraphObservatory",
        root / "Tests/GraphObservatory",
        root / "docs/graph-observatory-spec.md",
    )
    for old_path in old_paths:
        if old_path.exists():
            errors.append(f"legacy GraphObservatory surface still exists: {old_path.relative_to(root)}")

    frontend = root / "Tools/ContextExplorer/frontend"
    app = (frontend / "app.js").read_text(encoding="utf-8")
    html = (frontend / "index.html").read_text(encoding="utf-8")
    css = (frontend / "styles.css").read_text(encoding="utf-8")
    build = (root / "Tools/ContextExplorer/build.py").read_text(encoding="utf-8")

    forbidden_frontend_tokens = (
        "innerHTML",
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "EventSource",
        "localStorage.setItem",
        "sessionStorage.setItem",
        'method: "POST"',
        'method: "DELETE"',
        "function execute(",
        "function dispatch(",
        "function route(",
        "function approve(",
        "function apply(",
    )
    frontend_source = app + "\n" + html
    for token in forbidden_frontend_tokens:
        if token in frontend_source:
            errors.append(f"Frontend must remain offline/read-only and non-authoritative; forbidden token: {token}")

    if "__CONTEXT_MAP__" not in html or "__CONTEXT_MAP__" not in app or "__CONTEXT_MAP__" not in build:
        errors.append("Frontend Context Map data injection marker is missing")
    for source_name, source in (("HTML", html), ("App", app), ("Build", build)):
        if "__CONTEXT_GRAPH__" in source:
            errors.append(f"{source_name} must not use legacy Context Graph injection vocabulary")
    if "const graph =" in app:
        errors.append("Frontend must use Context Map vocabulary instead of a generic graph runtime variable")
    if "explicitOneHopRelations" not in app:
        errors.append("Frontend must expose only the deterministic one-hop relation projection")
    if "metadata.related only" not in html:
        errors.append("Frontend must disclose that relation projection comes only from explicit metadata.related")
    if "__HUMAN_ARCHITECTURE__" not in html:
        errors.append("Frontend Human Architecture data injection marker is missing")

    required_surface_ids = (
        "overview",
        "task-demo",
        "explore",
        "concept-flow",
        "tour-panel",
        "system-stack",
        "relations",
        "relation-projection-note",
    )
    for surface_id in required_surface_ids:
        if f'id="{surface_id}"' not in html:
            errors.append(f"Human Architecture surface is missing: {surface_id}")

    concept_ids = tuple(concept.get("id") for concept in architecture.get("concepts", []))
    if concept_ids != EXPECTED_CONCEPTS:
        errors.append(f"Human Architecture concepts must remain the 7-item mental model: {EXPECTED_CONCEPTS}")
    if len(architecture.get("tour", [])) < len(EXPECTED_CONCEPTS):
        errors.append("Guided tour does not cover the full Human Architecture mental model")
    if not architecture.get("task_demo", {}).get("steps"):
        errors.append("Task Demo must contain at least one walkthrough step")
    if "prefers-reduced-motion" not in css:
        errors.append("Frontend must preserve reduced-motion accessibility support")

    _validate_schema_contract(root, errors)

    if errors:
        print("Context Explorer validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    context_map = load_context_map(root).to_dict()
    print(
        "Context Explorer validation passed: "
        f"{len(context_map['nodes'])} contexts / {len(context_map['edges'])} relations / "
        f"{len(architecture['concepts'])} concepts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
