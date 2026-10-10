#!/usr/bin/env python3
"""Validate semantic loop declarations and ownership boundaries."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

from unityagent.orchestration.loop.semantic_loop import validate_loop_definition

GRAPH_PATH = ROOT / "src/unityagent/orchestration/definitions/development-parent-graph.yaml"


def _forbidden_runtime_tokens() -> tuple[str, ...]:
    # Build detector strings without making this validator itself look like Runtime code.
    return (
        "from " + "unityagent.runtime",
        "import " + "unityagent.runtime",
        "sub" + "process.",
        "os." + "kill",
        "task" + "kill",
    )


def main() -> int:
    graph = yaml.safe_load(GRAPH_PATH.read_text(encoding="utf-8")) or {}
    errors: list[str] = []

    for loop in graph.get("local_loops") or []:
        try:
            validate_loop_definition(loop)
        except Exception as exc:
            errors.append(f"{loop.get('id', '<unknown>')}: {exc}")

    graph_dir = ROOT / "src/unityagent/orchestration/graph"
    for legacy in ("local_loop.py", "todo_selector.py"):
        if (graph_dir / legacy).exists():
            errors.append(f"legacy Graph loop authority still exists: src/unityagent/orchestration/graph/{legacy}")

    loop_dir = ROOT / "src/unityagent/orchestration/loop"
    for path in loop_dir.glob("*.py"):
        if path.name == "validate.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in _forbidden_runtime_tokens():
            if token in text:
                errors.append(f"{path.relative_to(ROOT)} contains forbidden Runtime authority token: {token}")

    if errors:
        print("Loop Engineering validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Loop Engineering validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
