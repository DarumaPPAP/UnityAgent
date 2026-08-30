#!/usr/bin/env python3
"""Validate a reviewed Phase 9 BaselineFreeze manifest without executing Runtime."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Eval.Rebaseline.baseline_freeze import BaselineFreezeError, validate_baseline_freeze  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        value = yaml.safe_load(args.manifest.read_text(encoding="utf-8")) or {}
        if not isinstance(value, dict):
            raise BaselineFreezeError("BaselineFreeze manifest must be a YAML mapping")
        validate_baseline_freeze(value)
        print(
            f"Phase 9 BaselineFreeze valid: freeze_id={value['freeze_id']} "
            f"run_id={value['accepted_run']['run_id']}"
        )
        return 0
    except (OSError, ValueError, yaml.YAMLError, BaselineFreezeError) as exc:
        print(f"Phase 9 BaselineFreeze validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
