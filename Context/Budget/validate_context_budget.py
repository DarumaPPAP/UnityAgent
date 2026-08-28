#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import yaml
from context_budget_validation import validate_budget_integrity

ROOT = Path(__file__).resolve().parents[2]

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a canonical Context Budget report.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8")) or {}
    report = yaml.safe_load(args.report.read_text(encoding="utf-8")) or {}
    errors = validate_budget_integrity(ROOT, manifest, report)
    if errors:
        print("Context Budget validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Context Budget validation passed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
