#!/usr/bin/env python3
"""Exercise external_reference and context_include through the Context Manifest runtime."""

from __future__ import annotations

import sys
from pathlib import Path

from context_manifest_runtime import (
    ManifestError,
    build_manifest,
    load_yaml,
    project_execution_graph,
    validate_manifest,
)
from execution_graph_validator import validate_execution_graph


ROOT = Path(__file__).resolve().parents[2]
REQUEST = ROOT / "Tests" / "ContextManifest" / "requests" / "visual-context-include.yaml"


def main() -> int:
    errors: list[str] = []
    try:
        manifest = build_manifest(ROOT, load_yaml(REQUEST))
        errors.extend(validate_manifest(ROOT, manifest))

        external = manifest.get("context", {}).get("external_references", []) or []
        external_keys = {
            (item.get("repository"), item.get("path"), item.get("requirement"))
            for item in external
            if isinstance(item, dict)
        }
        expected_external = {
            ("DarumaPPAP/Beautiful-Definition", "AGENTS.md", "required"),
            ("DarumaPPAP/Beautiful-Definition", "Catalog/definitions.yaml", "required"),
        }
        if external_keys != expected_external:
            errors.append(f"Visual external references mismatch: {sorted(external_keys)}")

        includes = manifest.get("context", {}).get("context_includes", []) or []
        if len(includes) != 1:
            errors.append(f"Expected one Context include; found {len(includes)}")
        elif (
            includes[0].get("context_id") != "shader-change"
            or includes[0].get("requirement") != "conditional"
            or includes[0].get("condition") != "shader_or_material_work"
            or includes[0].get("source_path") != ".ai/context-packs/shader-change.yaml"
        ):
            errors.append(f"Context include projection mismatch: {includes[0]}")

        if manifest.get("task", {}).get("route") != "visual-direction":
            errors.append("context_include must not change the Primary Route.")
        if manifest.get("context", {}).get("route_handoffs"):
            errors.append("context_include must not emit a route_handoff.")

        graph = project_execution_graph(
            ROOT,
            manifest,
            "Artifacts/ContextManifests/golden-visual-context-include-a1.yaml",
        )
        errors.extend(validate_execution_graph(ROOT, graph))
        if not any(edge.get("type") == "includes_context" for edge in graph.get("edges", [])):
            errors.append("Execution Graph must project context_include as includes_context.")
        if any(edge.get("type") == "hands-off-to" for edge in graph.get("edges", [])):
            errors.append("Context include fixture must not project hands-off-to.")
        if not any(node.get("type") == "external_reference" for node in graph.get("nodes", [])):
            errors.append("Execution Graph must contain external_reference nodes.")

    except ManifestError as exc:
        errors.extend(exc.errors)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"Typed Context runtime self-test crashed: {exc}")

    if errors:
        print("Typed Context runtime validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Typed Context runtime validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
