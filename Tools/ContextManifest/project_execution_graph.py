#!/usr/bin/env python3
"""Project a validated Context Manifest into a derived Execution Graph YAML."""

from __future__ import annotations

import argparse
from pathlib import Path

from context_manifest_runtime import (
    ManifestError,
    dump_yaml,
    load_yaml,
    project_execution_graph,
)
from execution_graph_validator import validate_execution_graph


ROOT = Path(__file__).resolve().parents[2]


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        manifest_path = resolve_path(args.manifest)
        output_path = resolve_path(args.output)
        manifest = load_yaml(manifest_path)
        try:
            manifest_source = manifest_path.relative_to(ROOT).as_posix()
        except ValueError:
            manifest_source = manifest_path.as_posix()
        graph = project_execution_graph(ROOT, manifest, manifest_source)
        graph_errors = validate_execution_graph(ROOT, graph)
        if graph_errors:
            raise ManifestError(graph_errors)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(dump_yaml(graph), encoding="utf-8")
        print(f"Execution Graph built: {output_path}")
        return 0
    except ManifestError as exc:
        print("Execution Graph projection failed:")
        for error in exc.errors:
            print(f"- {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
