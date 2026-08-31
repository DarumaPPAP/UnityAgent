#!/usr/bin/env python3
"""Build and validate the read-only Context Explorer bundle."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from builder.graph_builder import AgentGraph
from context_projection import build_context_graph
from validate_graph import validate_graph


def build(root: Path, view: str) -> AgentGraph:
    if view != "context":
        raise ValueError("Only --view context is currently supported")
    return build_context_graph(root)


def write_bundle(root: Path, graph: AgentGraph, output_dir: Path) -> None:
    frontend = root / "Tools/GraphObservatory/frontend"
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_json = json.dumps(graph.to_dict(), ensure_ascii=False, sort_keys=True)
    for name in ("index.html", "styles.css", "app.js"):
        text = (frontend / name).read_text(encoding="utf-8")
        text = text.replace("window.__CONTEXT_GRAPH__ = null;", f"window.__CONTEXT_GRAPH__ = {graph_json};")
        (output_dir / name).write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--view", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    graph = build(root, args.view)
    document = graph.to_dict()
    errors = validate_graph(document)
    if errors:
        for error in errors:
            print(f"Graph validation failed: {error}")
        return 1
    if args.check:
        print(f"Context projection valid: {len(document['nodes'])} nodes / {len(document['edges'])} edges")
        return 0
    output = args.output or root / "Artifacts/GraphObservatory/context.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(graph.to_json(), encoding="utf-8")
    if args.bundle:
        write_bundle(root, graph, args.bundle)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
