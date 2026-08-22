#!/usr/bin/env python3
"""Build one budgeted Context Manifest from a runtime request."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from context_manifest_runtime import (
    ManifestError,
    build_manifest,
    dump_yaml,
    load_yaml,
    project_execution_graph,
)
from execution_graph_validator import validate_execution_graph


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "Artifacts" / "ContextManifests"
sys.path.insert(0, str(ROOT / "Tools" / "ContextBudget"))

from context_budget_runtime import BudgetError, build_budget_report  # noqa: E402
from context_budget_validation import validate_budget_integrity  # noqa: E402


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(data), encoding="utf-8")


def validate_previous_budget(previous: dict | None) -> None:
    if previous is None:
        return
    budget = previous.get("budget")
    if not isinstance(budget, dict):
        raise ManifestError(["Retry requires a previous canonical Manifest with Context Budget report."])
    errors = validate_budget_integrity(ROOT, previous, budget)
    if errors:
        raise ManifestError([f"Invalid previous Context Budget: {error}" for error in errors])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Manifest request YAML path")
    parser.add_argument("--previous", help="Previous Context Manifest for a retry attempt")
    parser.add_argument("--output", help="Output manifest path")
    parser.add_argument("--graph-output", help="Optional Execution Graph output path")
    args = parser.parse_args()

    try:
        request_path = resolve_path(args.request)
        request = load_yaml(request_path)
        previous = load_yaml(resolve_path(args.previous)) if args.previous else None
        validate_previous_budget(previous)
        manifest = build_manifest(ROOT, request, previous)

        budget = build_budget_report(ROOT, manifest, request)
        manifest["budget"] = budget
        budget_errors = validate_budget_integrity(ROOT, manifest, budget)
        if budget_errors:
            raise ManifestError(budget_errors)

        if args.output:
            output_path = resolve_path(args.output)
        else:
            output_path = DEFAULT_OUTPUT_ROOT / f"{manifest['manifest']['id']}.yaml"
        write_yaml(output_path, manifest)

        if args.graph_output:
            graph_path = resolve_path(args.graph_output)
            try:
                manifest_source = output_path.relative_to(ROOT).as_posix()
            except ValueError:
                manifest_source = output_path.as_posix()
            graph = project_execution_graph(ROOT, manifest, manifest_source)
            graph_errors = validate_execution_graph(ROOT, graph)
            if graph_errors:
                raise ManifestError(graph_errors)
            write_yaml(graph_path, graph)

        print(f"Context Manifest built: {output_path}")
        print(
            "Context Budget: "
            f"{budget['decision']} "
            f"({budget['context']['estimated_tokens']} estimated tokens, profile={budget['profile']})"
        )
        if args.graph_output:
            print(f"Execution Graph built: {graph_path}")
        return 0
    except BudgetError as exc:
        print("Context Budget build failed:")
        for error in exc.errors:
            print(f"- {error}")
        return 1
    except ManifestError as exc:
        print("Context Manifest build failed:")
        for error in exc.errors:
            print(f"- {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
