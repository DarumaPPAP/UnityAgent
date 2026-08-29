#!/usr/bin/env python3
"""Build one Phase 9 RebaselineSummary from already-observed run artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Eval.Rebaseline.rebaseline import (  # noqa: E402
    EXPECTED_CASES,
    RebaselineError,
    build_rebaseline_summary,
)

RUN_ROOT = ROOT / "Artifacts/ProductionSmoke"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RebaselineError(f"expected JSON object: {path}")
    return value


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise RebaselineError(f"expected YAML mapping: {path}")
    return value


def _fingerprints(run_root: Path) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for task_id in EXPECTED_CASES:
        manifest_path = run_root / task_id / "context-manifest.yaml"
        if not manifest_path.is_file():
            continue
        manifest = _yaml(manifest_path)
        fingerprint = ((manifest.get("context") or {}).get("definition_fingerprint"))
        if isinstance(fingerprint, dict):
            output[task_id] = fingerprint
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", required=True)
    parser.add_argument("--codex-version", required=True)
    parser.add_argument("--historical-replay", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-baseline-ready", action="store_true")
    args = parser.parse_args()

    run_root = (RUN_ROOT / args.run_id).resolve()
    try:
        run_root.relative_to(RUN_ROOT.resolve())
        if not run_root.is_dir():
            raise RebaselineError(f"Production Smoke run does not exist: {run_root}")
        eval_path = run_root / "eval-summary.json"
        if not eval_path.is_file():
            raise RebaselineError(f"missing Eval summary: {eval_path}")
        historical = None
        if args.historical_replay:
            historical = _json(args.historical_replay.resolve())
        summary = build_rebaseline_summary(
            _json(eval_path),
            run_id=args.run_id,
            source_revision=args.source_revision,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            codex_version=args.codex_version,
            definition_fingerprints=_fingerprints(run_root),
            historical_replay=historical,
        )
        output = args.output or (run_root / "rebaseline-summary.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.require_baseline_ready and not summary["baseline"]["eligible"]:
            return 1
        return 0
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError, RebaselineError) as exc:
        print(f"Phase 9 RebaselineSummary build failed: {exc}", file=sys.stderr)
        return 30


if __name__ == "__main__":
    raise SystemExit(main())
