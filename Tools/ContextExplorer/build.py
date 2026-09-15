#!/usr/bin/env python3
"""Build the read-only UnityAgent Context Explorer map and offline viewer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from architecture_projection import build_human_architecture
from context_map import ContextMap, load_context_map, validate_context_map


DEFAULT_ARTIFACT = Path("Artifacts/ContextExplorer/context-map.json")


def write_bundle(root: Path, context_map: ContextMap, architecture: dict, output_dir: Path) -> None:
    """Write a fully static bundle with projected data embedded in index.html."""
    frontend = root / "Tools/ContextExplorer/frontend"
    output_dir.mkdir(parents=True, exist_ok=True)
    map_json = json.dumps(context_map.to_dict(), ensure_ascii=False, sort_keys=True)
    architecture_json = json.dumps(architecture, ensure_ascii=False, sort_keys=True)

    for name in ("index.html", "styles.css", "app.js"):
        text = (frontend / name).read_text(encoding="utf-8")
        text = text.replace("window.__CONTEXT_GRAPH__ = null;", f"window.__CONTEXT_GRAPH__ = {map_json};")
        text = text.replace(
            "window.__HUMAN_ARCHITECTURE__ = null;",
            f"window.__HUMAN_ARCHITECTURE__ = {architecture_json};",
        )
        (output_dir / name).write_text(text, encoding="utf-8")

    (output_dir / "context-map.json").write_text(context_map.to_json(), encoding="utf-8")


def build(root: Path) -> tuple[ContextMap, dict]:
    context_map = load_context_map(root)
    architecture = build_human_architecture(root)
    return context_map, architecture


def main() -> int:
    parser = argparse.ArgumentParser(description="Build UnityAgent Context Explorer")
    parser.add_argument("--output", type=Path, help="context-map.json output path")
    parser.add_argument("--bundle", type=Path, help="static offline viewer directory")
    parser.add_argument("--check", action="store_true", help="validate without writing artifacts")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    context_map, architecture = build(root)
    document = context_map.to_dict()
    errors = validate_context_map(document)
    if errors:
        print("Context Explorer map validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    if args.check:
        print(
            "Context Explorer valid: "
            f"{len(document['nodes'])} contexts / {len(document['edges'])} relations / "
            f"{len(architecture['concepts'])} human concepts"
        )
        return 0

    output = args.output or root / DEFAULT_ARTIFACT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(context_map.to_json(), encoding="utf-8")

    if args.bundle:
        write_bundle(root, context_map, architecture, args.bundle)

    print(f"Wrote {output.relative_to(root) if output.is_relative_to(root) else output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
