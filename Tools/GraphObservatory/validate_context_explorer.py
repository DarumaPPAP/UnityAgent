#!/usr/bin/env python3
"""Validate Context Explorer projection and static read-only surface."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from context_projection import build_context_graph  # noqa: E402
from validate_graph import validate_graph  # noqa: E402


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate_graph(build_context_graph(root).to_dict())
    app = (root / "Tools/GraphObservatory/frontend/app.js").read_text(encoding="utf-8")
    html = (root / "Tools/GraphObservatory/frontend/index.html").read_text(encoding="utf-8")
    if "innerHTML" in app or "fetch(" in app or "XMLHttpRequest" in app:
        errors.append("Frontend must remain offline and text-content based")
    if "__CONTEXT_GRAPH__" not in html:
        errors.append("Frontend data injection marker is missing")
    if errors:
        print("Context Explorer validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Context Explorer validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
