#!/usr/bin/env python3
"""Record one Quality Gate result into an existing Context Manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from context_manifest_runtime import (
    ManifestError,
    apply_gate_evidence,
    dump_yaml,
    load_yaml,
    project_execution_graph,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[2]


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(data), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--status", required=True, choices=("passed", "failed", "unavailable"))
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--source-path")
    parser.add_argument("--remaining-validation")
    parser.add_argument("--failure-reason")
    parser.add_argument("--output", help="Defaults to overwriting --manifest")
    parser.add_argument("--graph-output", help="Optional refreshed Execution Graph output")
    args = parser.parse_args()

    try:
        manifest_path = resolve_path(args.manifest)
        manifest = load_yaml(manifest_path)
        updated = apply_gate_evidence(
            ROOT,
            manifest,
            gate=args.gate,
            status=args.status,
            evidence_id=args.evidence_id,
            reason=args.reason,
            source_path=args.source_path,
            remaining_validation=args.remaining_validation,
            failure_reason=args.failure_reason,
        )
        errors = validate_manifest(ROOT, updated)
        if errors:
            raise ManifestError(errors)

        output_path = resolve_path(args.output) if args.output else manifest_path
        write_yaml(output_path, updated)

        if args.graph_output:
            graph_path = resolve_path(args.graph_output)
            try:
                manifest_source = output_path.relative_to(ROOT).as_posix()
            except ValueError:
                manifest_source = output_path.as_posix()
            graph = project_execution_graph(ROOT, updated, manifest_source)
            write_yaml(graph_path, graph)

        print(f"Context Manifest evidence recorded: {output_path}")
        print(f"Execution status: {updated['execution']['status']}")
        return 0
    except ManifestError as exc:
        print("Context Manifest evidence update failed:")
        for error in exc.errors:
            print(f"- {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
