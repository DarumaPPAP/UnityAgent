#!/usr/bin/env python3
"""Build a read-only UnityAgent to Loop handoff from JSON inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from handoff import build_to_loop


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task = json.loads(args.task.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    harness = json.loads(args.harness.read_text(encoding="utf-8"))
    output = build_to_loop(task, manifest, harness)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
