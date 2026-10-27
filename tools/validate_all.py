#!/usr/bin/env python3
"""Run only the currently supported bootstrap/connection/read Smoke contract.

This is NOT an all-product regression or Unity Editor E2E gate.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "tests/smoke"


def main() -> int:
    parser = argparse.ArgumentParser(description="UnityAgent smoke-only verification")
    parser.add_argument(
        "--profile", choices=("smoke",), default="smoke",
        help="Only bootstrap/connection/read-only smoke is supported",
    )
    parser.parse_args()
    required = [SMOKE / f"test_{name}.py" for name in ("bootstrap", "connection", "read")]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        print("SMOKE_BLOCKED: required test files are missing: " + ", ".join(missing), file=sys.stderr)
        return 2
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(SMOKE),
         "-p", "test_*.py", "-q", "-b"],
        cwd=ROOT, check=False,
    )
    if result.returncode:
        return result.returncode
    print("SMOKE_PASS (host only): bootstrap, connection, read. "
          "Mutation/Approval/Unity Editor/Player/Device regression NOT VERIFIED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
