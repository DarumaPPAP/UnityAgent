#!/usr/bin/env python3
"""Emit one deterministic Effective Harness document."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from effective_harness import build_effective_harness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    request = yaml.safe_load(args.request.read_text(encoding="utf-8")) if args.request else {}
    document = build_effective_harness(root, args.contract, args.profile, request or {})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
