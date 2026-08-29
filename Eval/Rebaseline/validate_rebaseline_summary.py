#!/usr/bin/env python3
"""Validate an existing Phase 9 RebaselineSummary without executing Runtime."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Eval.Rebaseline.rebaseline import RebaselineError, validate_rebaseline_summary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--require-baseline-ready", action="store_true")
    args = parser.parse_args()
    try:
        value = json.loads(args.summary.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RebaselineError("RebaselineSummary must be a JSON object")
        validate_rebaseline_summary(value)
        if args.require_baseline_ready and not value["baseline"]["eligible"]:
            print("Phase 9 RebaselineSummary is valid but not baseline_ready.", file=sys.stderr)
            return 1
        print(
            f"Phase 9 RebaselineSummary valid: status={value['status']} "
            f"eligible={value['baseline']['eligible']}"
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RebaselineError) as exc:
        print(f"Phase 9 RebaselineSummary validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
