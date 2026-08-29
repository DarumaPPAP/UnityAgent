#!/usr/bin/env python3
"""Grade already-observed Actual Behavior candidate results.

This canonical Phase-6 entrypoint never launches Runtime, Codex, Unity, or an
external adapter. Production execution happens first through Runtime; Eval
consumes the resulting facts/artifacts afterward.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "Eval" / "Golden"
for path in (ROOT, GOLDEN_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core_run_golden_evals import infer_failures  # noqa: E402

CASES_PATH = ROOT / "Eval" / "Datasets" / "Golden" / "cases.yaml"
DEFAULT_OUTPUT = ROOT / "Artifacts" / "Eval" / "Behavior" / "summary.json"
INFRASTRUCTURE_FAILURES = {
    "runtime_timeout", "runtime_protocol_failure", "runtime_cancelled",
    "runtime_tool_unavailable", "runtime_permission_denied",
    "evaluator_contract_failure", "task_fixture_invalid",
    "unavailable_required_evidence",
}


class BehaviorEvalError(ValueError):
    pass


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise BehaviorEvalError(f"expected mapping: {path}")
    return value


def _observation_state(result: dict[str, Any]) -> str:
    execution = result.get("execution") or {}
    state = str(execution.get("observation_state") or "observed")
    if state not in {"observed", "not_observed"}:
        raise BehaviorEvalError(f"invalid observation_state: {state}")
    return state


def evaluate_results(result_document: dict[str, Any], *, cases_path: Path = CASES_PATH) -> dict[str, Any]:
    case_document = _yaml(cases_path)
    cases = {str(case.get("id")): case for case in case_document.get("cases", []) or []}
    results = result_document.get("results") or []
    if not isinstance(results, list):
        raise BehaviorEvalError("results must be an array")

    graded: list[dict[str, Any]] = []
    detail_counts: Counter[str] = Counter()
    quality_denominator = 0
    quality_passed = 0

    for result in results:
        if not isinstance(result, dict):
            raise BehaviorEvalError("result entry must be an object")
        task_id = str(result.get("task_id") or "")
        case = cases.get(task_id)
        if case is None:
            failures = ["broken_eval"]
            naming_findings: list[dict[str, Any]] = []
            observation_state = "not_observed"
            eligible = False
        else:
            failures, naming_findings = infer_failures(case, result)
            observation_state = _observation_state(result)
            eligible = observation_state == "observed" and not (set(failures) & INFRASTRUCTURE_FAILURES)

        status = "passed" if not failures else "failed"
        if eligible:
            quality_denominator += 1
            if status == "passed":
                quality_passed += 1
        detail_counts.update(failures)
        graded.append({
            "task_id": task_id,
            "status": status,
            "observation_state": observation_state,
            "quality_denominator_eligible": eligible,
            "failure_details": failures,
            "naming_findings": naming_findings,
        })

    total = len(graded)
    overall_passed = sum(item["status"] == "passed" for item in graded)
    return {
        "schema_version": "1.0",
        "total": total,
        "overall_passed": overall_passed,
        "overall_failed": total - overall_passed,
        "quality_denominator": quality_denominator,
        "quality_passed": quality_passed,
        "regression_pass_rate": (quality_passed / quality_denominator) if quality_denominator else 0.0,
        "not_observed_count": sum(item["observation_state"] == "not_observed" for item in graded),
        "failure_counts": dict(sorted(detail_counts.items())),
        "results": graded,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        summary = evaluate_results(_yaml(args.results))
    except (OSError, yaml.YAMLError, BehaviorEvalError, ValueError) as exc:
        print(f"Behavior Eval failed: {exc}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["overall_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
