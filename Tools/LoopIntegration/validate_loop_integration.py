#!/usr/bin/env python3
"""Validate the UnityAgent / Unity-Graph-Engineering handoff contract."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    path = root / ".ai/integrations/unity-graph-engineering.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []
    for direction in ("unityagent_to_loop", "loop_to_unityagent"):
        if not document.get(direction, {}).get("required"):
            errors.append(f"{direction}.required is missing")
    if document.get("ownership_invariants", {}).get("loop_engine_is_not_duplicated") is not True:
        errors.append("Loop ownership invariant is missing")
    if errors:
        print("Loop integration validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Loop integration validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
