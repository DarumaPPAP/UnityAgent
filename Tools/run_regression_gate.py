#!/usr/bin/env python3
"""Stable user-facing entry point for the local Production regression gate.

The implementation may move internally without changing the command documented
for users. Keep user-facing documentation pointed at this file rather than an
implementation directory tied to a development phase.
"""
from __future__ import annotations

import runpy
from pathlib import Path


IMPLEMENTATION = Path(__file__).resolve().parent / "Phase10" / "run_local_regression_gate.py"


def main() -> int:
    if not IMPLEMENTATION.is_file():
        raise FileNotFoundError(f"Regression gate implementation not found: {IMPLEMENTATION}")
    runpy.run_path(str(IMPLEMENTATION), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
