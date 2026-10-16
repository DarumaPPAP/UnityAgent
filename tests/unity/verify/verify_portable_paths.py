#!/usr/bin/env python3
"""Reject developer-machine absolute paths from the production surface."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_MACHINE_PATH = re.compile(r"(?i)\b[A-Z]:[\\/](?:Users|home)[\\/]|/(?:Users|home)/")


def tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = [Path(item) for item in completed.stdout.decode("utf-8").split("\0") if item]
    return [path for path in paths if not path.parts or path.parts[0] != "Legacy"]


def main() -> int:
    violations: list[str] = []
    for relative_path in tracked_files():
        path = ROOT / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            if FORBIDDEN_MACHINE_PATH.search(line):
                violations.append(f"{relative_path}:{line_number}: machine-specific absolute path")

    if violations:
        for violation in violations:
            print(f"[ERROR] {violation}")
        return 1

    print("Production surface portable-path contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
