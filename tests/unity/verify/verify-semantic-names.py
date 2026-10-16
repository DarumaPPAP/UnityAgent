#!/usr/bin/env python3
"""Keep the current Artist surface semantic and free of legacy tool names."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = [ROOT / "Packages/com.darumappap.artist-subagent/Editor", ROOT / "cli/artist"]
FORBIDDEN = re.compile(r"McpForUnityTool|com\.coplaydev\.unity-mcp|AutoRegister|UnityGraphicsMcp", re.IGNORECASE)
violations = []

for scan_root in SCAN_ROOTS:
    if not scan_root.is_dir():
        continue
    for path in scan_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".cs", ".asmdef", ".json"}:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

if violations:
    print("Semantic naming violations detected:")
    print("\n".join(violations))
    sys.exit(1)

print("UnityArtistCLI semantic naming guard passed.")
