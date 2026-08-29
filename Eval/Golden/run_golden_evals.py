#!/usr/bin/env python3
"""Canonical Golden Eval entrypoint backed by Eval/Datasets/Golden."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "Eval" / "Golden"
for path in (ROOT, GOLDEN_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import core_run_golden_evals as core  # noqa: E402
from Eval.Datasets.paths import GOLDEN_ROOT  # noqa: E402

core.CASES_PATH = GOLDEN_ROOT / "cases.yaml"


def main() -> int:
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
