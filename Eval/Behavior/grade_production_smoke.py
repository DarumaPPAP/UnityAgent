#!/usr/bin/env python3
"""Grade an already-executed one-repo Production Smoke run.

This entrypoint never launches Runtime or Codex. It normalizes immutable case evidence
and passes the resulting candidate facts to the canonical Behavior evaluator.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = ROOT / "Artifacts/ProductionSmoke"
SUITES = ROOT / "Eval/Datasets/Behavior/suites.yaml"
NORMALIZER = ROOT / "Eval/Behavior/normalize_result.py"
EVALUATOR = ROOT / "Eval/Behavior/run_behavior_eval.py"


class ProductionSmokeGradeError(ValueError):
    pass


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ProductionSmokeGradeError(f"expected YAML mapping: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    run_root = (RUN_ROOT / args.run_id).resolve()
    try:
        run_root.relative_to(RUN_ROOT.resolve())
        if not run_root.is_dir():
            raise ProductionSmokeGradeError(f"Production Smoke run does not exist: {run_root}")
        suite = ((_yaml(SUITES).get("suites") or {}).get("production_smoke") or {})
        task_ids = [str(item.get("golden_task_id") or "") for item in suite.get("cases") or []]
        candidate_dir = run_root / "candidate"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, Any]] = []
        for task_id in task_ids:
            case_dir = run_root / task_id
            if not case_dir.is_dir():
                raise ProductionSmokeGradeError(f"missing Production Smoke case evidence: {task_id}")
            output = candidate_dir / f"{task_id}.yaml"
            completed = subprocess.run(
                [sys.executable, str(NORMALIZER), "--case-dir", str(case_dir), "--golden-task-id", task_id,
                 "--suite", "production_smoke", "--output", str(output)],
                cwd=ROOT, check=False,
            )
            if completed.returncode != 0 or not output.is_file():
                raise ProductionSmokeGradeError(f"normalization failed for {task_id}")
            results.append(_yaml(output))
        candidate_document = {"schema_version": "1.0", "results": results}
        candidate_path = run_root / "candidate-results.yaml"
        candidate_path.write_text(yaml.safe_dump(candidate_document, sort_keys=False, allow_unicode=True), encoding="utf-8")
        summary_path = run_root / "eval-summary.json"
        completed = subprocess.run(
            [sys.executable, str(EVALUATOR), "--results", str(candidate_path), "--output", str(summary_path)],
            cwd=ROOT, check=False,
        )
        if not summary_path.is_file():
            raise ProductionSmokeGradeError("canonical Behavior Eval did not produce a summary")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return completed.returncode
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"Production Smoke grading failed: {exc}", file=sys.stderr)
        return 30


if __name__ == "__main__":
    raise SystemExit(main())
