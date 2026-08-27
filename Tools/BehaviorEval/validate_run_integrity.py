#!/usr/bin/env python3
"""Regression-check immutable Actual Behavior run directories."""

from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from run_behavior_eval import BehaviorRunError, _create_fresh_run_root, _safe_run_root


def main() -> int:
    run_id = f"integrity-validator-{uuid.uuid4().hex}"
    run_root = _safe_run_root(run_id)

    try:
        _create_fresh_run_root(run_root)
        marker = run_root / "sentinel.txt"
        marker.write_text("original evidence\n", encoding="utf-8")

        try:
            _create_fresh_run_root(run_root)
        except BehaviorRunError as exc:
            if "immutable" not in str(exc):
                print(f"[FAIL] Unexpected reuse error: {exc}")
                return 1
        else:
            print("[FAIL] Existing Behavior Eval run directory was reused.")
            return 1

        if marker.read_text(encoding="utf-8") != "original evidence\n":
            print("[FAIL] Existing run evidence was modified during reuse rejection.")
            return 1

        print("Behavior Eval run integrity validation passed.")
        return 0
    finally:
        if run_root.exists():
            shutil.rmtree(run_root)


if __name__ == "__main__":
    raise SystemExit(main())
