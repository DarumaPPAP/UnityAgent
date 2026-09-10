#!/usr/bin/env python3
"""Run local reference selection or build a local-first incident plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Context.Retrieval.Reference.reference_navigator import (  # noqa: E402
    ReferenceSnapshotError,
    build_investigation_plan,
    load_snapshot,
    search_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Use a local MyResourceCenter reference snapshot")
    parser.add_argument("--snapshot", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--question")
    mode.add_argument("--symptom")
    parser.add_argument("--environment", default="")
    parser.add_argument("--tier", choices=("default", "investigation"), default="default")
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--max-hypotheses", type=int, default=5)
    parser.add_argument("--max-context-characters", type=int, default=8000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        snapshot = load_snapshot(args.snapshot)
        if args.symptom is not None:
            result = build_investigation_plan(
                snapshot,
                args.symptom,
                environment=args.environment,
                max_hypotheses=args.max_hypotheses,
                max_context_characters=max(args.max_context_characters, 256),
            )
        else:
            result = search_snapshot(
                snapshot,
                args.question,
                tier=args.tier,
                max_items=args.max_items,
                max_context_characters=args.max_context_characters,
            )
    except ReferenceSnapshotError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
