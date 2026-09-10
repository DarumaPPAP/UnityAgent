#!/usr/bin/env python3
"""Validate Context Explorer projection and static read-only surface."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from architecture_projection import build_human_architecture  # noqa: E402
from context_projection import build_context_graph  # noqa: E402
from validate_graph import validate_graph  # noqa: E402


EXPECTED_CONCEPTS = ("rules", "planner", "knowledge", "executor", "evidence", "memory", "quality")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate_graph(build_context_graph(root).to_dict())
    architecture = build_human_architecture(root)
    app = (root / "Tools/GraphObservatory/frontend/app.js").read_text(encoding="utf-8")
    html = (root / "Tools/GraphObservatory/frontend/index.html").read_text(encoding="utf-8")
    css = (root / "Tools/GraphObservatory/frontend/styles.css").read_text(encoding="utf-8")

    forbidden_frontend_tokens = ("innerHTML", "fetch(", "XMLHttpRequest", "localStorage.setItem", "sessionStorage.setItem")
    for token in forbidden_frontend_tokens:
        if token in app:
            errors.append(f"Frontend must remain offline/read-only; forbidden token: {token}")

    if "__CONTEXT_GRAPH__" not in html:
        errors.append("Frontend Context data injection marker is missing")
    if "__HUMAN_ARCHITECTURE__" not in html:
        errors.append("Frontend Human Architecture data injection marker is missing")

    required_surface_ids = ("overview", "task-demo", "explore", "concept-flow", "tour-panel", "system-stack")
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

    if errors:
        print("Context Explorer validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "Context Explorer validation passed: "
        f"{len(architecture['concepts'])} concepts / "
        f"{len(architecture['tour'])} tour steps / "
        f"{len(architecture['task_demo']['steps'])} demo steps."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
