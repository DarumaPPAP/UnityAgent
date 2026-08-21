#!/usr/bin/env python3
"""Validate every Task Contract's Effective Harness projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from effective_harness import build_effective_harness, validate_effective_harness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--contract")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    contracts = sorted((root / ".ai/harness/task-contracts").glob("*.yaml")) if args.all or not args.contract else [root / args.contract]
    errors: list[str] = []
    for path in contracts:
        if path.name == "task-contract.schema.yaml":
            continue
        relative = path.relative_to(root).as_posix()
        try:
            document = build_effective_harness(root, relative)
            errors.extend(f"{relative}: {error}" for error in validate_effective_harness(document))
            json.dumps(document, sort_keys=True)
        except Exception as exc:  # noqa: BLE001 - report every contract binding failure.
            errors.append(f"{relative}: {exc}")
    if errors:
        print("Effective Harness validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Effective Harness validation passed: {len(contracts)} contracts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
