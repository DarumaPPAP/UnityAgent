#!/usr/bin/env python3
"""Evaluate Phase 6 expansion evidence from a JSON metrics document."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from expansion_gate import evaluate_expansion_gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_expansion_gate(json.loads(args.metrics.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
