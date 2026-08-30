#!/usr/bin/env python3
"""Compare one candidate RebaselineSummary against the frozen Phase 9 baseline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Eval.Regression.baseline_comparator import (  # noqa: E402
    BaselineComparisonError,
    build_baseline_comparison,
)
from Eval.Rebaseline.baseline_freeze import BaselineFreezeError  # noqa: E402
from Eval.Rebaseline.rebaseline import RebaselineError  # noqa: E402

EXIT_BY_DECISION = {
    "PASS": 0,
    "BLOCK_REGRESSION": 10,
    "BLOCK_INCONCLUSIVE": 11,
    "REBASELINE_REQUIRED": 12,
}


def _yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise BaselineComparisonError(f"expected YAML mapping: {path}")
    return value


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BaselineComparisonError(f"expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-pass",
        action="store_true",
        help="return a non-zero gate-specific exit code unless the comparison decision is PASS",
    )
    args = parser.parse_args()

    try:
        comparison = build_baseline_comparison(
            _yaml(args.baseline.resolve()),
            _json(args.candidate.resolve()),
        )
        output = args.output or (args.candidate.resolve().parent / "baseline-comparison.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(comparison, ensure_ascii=False, indent=2))
        if args.require_pass:
            return EXIT_BY_DECISION[comparison["gate"]["decision"]]
        return 0
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        yaml.YAMLError,
        BaselineComparisonError,
        BaselineFreezeError,
        RebaselineError,
    ) as exc:
        print(f"Phase 10 baseline comparison failed: {exc}", file=sys.stderr)
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
