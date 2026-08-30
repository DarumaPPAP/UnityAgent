#!/usr/bin/env python3
"""Validate an existing Phase 10 BaselineComparison without executing Runtime."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Eval.Regression.baseline_comparator import (  # noqa: E402
    BaselineComparisonError,
    validate_baseline_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()
    try:
        value = json.loads(args.comparison.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise BaselineComparisonError("BaselineComparison must be a JSON object")
        validate_baseline_comparison(value)
        decision = value["gate"]["decision"]
        print(f"Phase 10 BaselineComparison valid: decision={decision}")
        if args.require_pass and decision != "PASS":
            return 1
        return 0
    except (OSError, ValueError, json.JSONDecodeError, BaselineComparisonError) as exc:
        print(f"Phase 10 BaselineComparison validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
