#!/usr/bin/env python3
"""Canonical Golden eval entrypoint backed by eval/datasets/Golden.

The mature Golden grader remains the implementation core. This module switches
its dataset authority and re-exports its public API so existing validators and
compatibility shims do not create a second grader implementation.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "eval" / "golden"
for path in (ROOT, GOLDEN_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import core_run_golden_evals as core  # noqa: E402
from eval.datasets.paths import GOLDEN_ROOT  # noqa: E402

core.CASES_PATH = GOLDEN_ROOT / "cases.yaml"

for _name in dir(core):
    if not _name.startswith("_") and _name not in {"CASES_PATH"}:
        globals()[_name] = getattr(core, _name)

CASES_PATH = core.CASES_PATH


def main() -> int:
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
