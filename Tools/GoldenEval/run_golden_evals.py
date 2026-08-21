#!/usr/bin/env python3
"""Grade UnityAgent candidate results against the Golden Regression suite."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
DEFAULT_OUTPUT = ROOT / "Artifacts" / "GoldenEval" / "summary.json"
KNOWN_FAILURE_TYPES = {
    "routing_miss",
    "context_miss",
    "policy_violation",
    "harness_violation",
    "mutation_violation",
    "evidence_overclaim",
    "model_failure",
    "broken_eval",
    "unavailable_evidence",
}


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def infer_failures(case: dict, result: dict) -> list[str]:
    expectation = case.get("expectation", {})
    failures: list[str] = []
    if expectation.get("route") and result.get("route") != expectation.get("route"):
        failures.append("routing_miss")

    applied_policies = set(result.get("applied_policies", []) or [])
    if not set(expectation.get("required_policies", []) or []).issubset(applied_policies):
        failures.append("policy_violation")

    signals = set(result.get("signals", []) or [])
    if not set(expectation.get("required_signals", []) or []).issubset(signals):
        failures.append("model_failure")
    if set(expectation.get("forbidden_signals", []) or []) & signals:
        failures.append("policy_violation")

    gates = result.get("gates", {}) or {}
    for gate in expectation.get("required_gates", []) or []:
        status = gates.get(gate)
        if status == "unavailable":
            failures.append("unavailable_evidence")
        elif status != "passed":
            failures.append("harness_violation")

    required_knowledge = set(expectation.get("required_knowledge", []) or [])
    loaded_knowledge = set(result.get("knowledge", []) or [])
    unresolved = set(result.get("unresolved", []) or [])
    for knowledge in required_knowledge:
        if knowledge not in loaded_knowledge and f"knowledge:{knowledge}" not in unresolved:
            failures.append("context_miss")

    for failure_type in result.get("failure_types", []) or []:
        if failure_type in KNOWN_FAILURE_TYPES:
            failures.append(str(failure_type))
        else:
            failures.append("broken_eval")

    if result.get("outcome") == "unavailable":
        failures.append("unavailable_evidence")
    elif result.get("outcome") != expectation.get("outcome", "passed"):
        failures.append("model_failure")

    return sorted(set(failures))


def rate(failure_counts: Counter[str], failure_type: str, total: int) -> float:
    return (failure_counts[failure_type] / total) if total else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, help="Candidate result YAML")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Summary JSON output")
    args = parser.parse_args()

    suite = load_yaml(CASES_PATH)
    result_doc = load_yaml(Path(args.results))
    cases = {case["id"]: case for case in suite.get("cases", []) or []}
    results = result_doc.get("results", []) or []

    graded: list[dict] = []
    failure_counts: Counter[str] = Counter()
    attempts = 0
    first_pass = 0

    for result in results:
        task_id = str(result.get("task_id", ""))
        case = cases.get(task_id)
        if case is None:
            graded.append({"task_id": task_id, "status": "broken_eval", "failures": ["broken_eval"]})
            failure_counts["broken_eval"] += 1
            continue
        failures = infer_failures(case, result)
        status = "passed" if not failures else "failed"
        attempt_count = max(1, int(result.get("attempt_count", 1)))
        attempts += attempt_count
        if status == "passed" and attempt_count == 1:
            first_pass += 1
        failure_counts.update(failures)
        graded.append({"task_id": task_id, "status": status, "failures": failures})

    total = len(graded)
    passed = sum(item["status"] == "passed" for item in graded)
    unavailable = sum("unavailable_evidence" in item["failures"] for item in graded)
    summary = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "regression_pass_rate": (passed / total) if total else 0.0,
        "first_pass_rate": (first_pass / total) if total else 0.0,
        "policy_violation_rate": rate(failure_counts, "policy_violation", total),
        "routing_miss_rate": rate(failure_counts, "routing_miss", total),
        "context_miss_rate": rate(failure_counts, "context_miss", total),
        "mutation_violation_rate": rate(failure_counts, "mutation_violation", total),
        "gate_failure_rate": rate(failure_counts, "harness_violation", total),
        "unavailable_rate": (unavailable / total) if total else 0.0,
        "retry_count": max(0, attempts - total),
        "failure_counts": dict(sorted(failure_counts.items())),
        "results": graded,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
