#!/usr/bin/env python3
"""Grade UnityAgent candidate results against the Golden Regression suite."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

from naming_grader import ArtifactEvidenceError, grade_generated_artifacts

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
DEFAULT_OUTPUT = ROOT / "Artifacts" / "GoldenEval" / "summary.json"
GOLDEN_ARTIFACT_ROOT = ROOT / "Artifacts" / "GoldenEval"
BEHAVIOR_ARTIFACT_ROOT = ROOT / "Artifacts" / "BehaviorEval"
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


def _is_actual_behavior(result: dict) -> bool:
    return str((result.get("execution", {}) or {}).get("mode") or "") == "actual_behavior"


def _naming_artifact_root(result: dict) -> Path:
    return BEHAVIOR_ARTIFACT_ROOT if _is_actual_behavior(result) else GOLDEN_ARTIFACT_ROOT


def infer_naming_failures(case: dict, result: dict) -> tuple[list[str], list[dict]]:
    if case.get("category") != "naming":
        return [], []

    naming_expectation = (case.get("expectation", {}) or {}).get("naming", {}) or {}
    artifacts = result.get("generated_artifacts", []) or []
    signals = set(result.get("signals", []) or [])

    # Actual Behavior no-new-Type cases are proven from the mutation/source extractor.
    # A modified existing source file is not a newly generated Type artifact, so an empty
    # generated_artifacts list is valid when deterministic evidence proves no Type creation.
    if _is_actual_behavior(result) and naming_expectation.get("require_no_new_type") and not artifacts:
        if "new_type_created" in signals:
            structure = ((result.get("execution", {}) or {}).get("structure", {}) or {})
            names = list(structure.get("new_type_names", []) or [])
            findings = [
                {
                    "code": "NAME005_UNEXPECTED_NEW_TYPE",
                    "identifier": name,
                    "severity": "error",
                    "message": "Actual Behavior evidence shows an unexpected new Type.",
                }
                for name in names
            ] or [
                {
                    "code": "NAME005_UNEXPECTED_NEW_TYPE",
                    "identifier": "",
                    "severity": "error",
                    "message": "Actual Behavior evidence shows an unexpected new Type.",
                }
            ]
            return ["policy_violation"], findings
        return [], []

    try:
        grade = grade_generated_artifacts(
            artifacts,
            naming_expectation,
            allowed_root=_naming_artifact_root(result),
        )
    except (ArtifactEvidenceError, OSError, UnicodeError) as exc:
        return ["broken_eval"], [
            {
                "code": "NAMING_ARTIFACT_EVIDENCE_ERROR",
                "identifier": "",
                "severity": "error",
                "message": str(exc),
            }
        ]

    failures: list[str] = []
    for finding in grade.get("errors", []) or []:
        if finding.get("code") == "NAME004_REQUIRED_IDENTIFIER_MISSING":
            failures.append("model_failure")
        else:
            failures.append("policy_violation")
    return sorted(set(failures)), list(grade.get("findings", []) or [])


def infer_failures(case: dict, result: dict) -> tuple[list[str], list[dict]]:
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

    naming_failures, naming_findings = infer_naming_failures(case, result)
    failures.extend(naming_failures)

    declared_failure_types: set[str] = set()
    for failure_type in result.get("failure_types", []) or []:
        if failure_type in KNOWN_FAILURE_TYPES:
            failures.append(str(failure_type))
            declared_failure_types.add(str(failure_type))
        else:
            failures.append("broken_eval")
            declared_failure_types.add("broken_eval")

    outcome = result.get("outcome")
    if outcome == "unavailable":
        failures.append("unavailable_evidence")
    elif outcome != expectation.get("outcome", "passed"):
        # Protocol failures remain broken_eval and are not relabeled as model failures.
        if "broken_eval" not in declared_failure_types and "unavailable_evidence" not in declared_failure_types:
            failures.append("model_failure")

    return sorted(set(failures)), naming_findings


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
    actual_behavior_count = 0
    actual_behavior_coverage: list[float] = []

    for result in results:
        task_id = str(result.get("task_id", ""))
        execution = result.get("execution", {}) or {}
        if _is_actual_behavior(result):
            actual_behavior_count += 1
            coverage = execution.get("evidence_coverage", {}) or {}
            if "rate" in coverage:
                actual_behavior_coverage.append(float(coverage.get("rate", 0.0)))

        case = cases.get(task_id)
        if case is None:
            graded.append(
                {
                    "task_id": task_id,
                    "status": "broken_eval",
                    "failures": ["broken_eval"],
                    "naming_findings": [],
                    "execution": execution,
                }
            )
            failure_counts["broken_eval"] += 1
            continue

        failures, naming_findings = infer_failures(case, result)
        status = "passed" if not failures else "failed"
        attempt_count = max(1, int(result.get("attempt_count", 1)))
        attempts += attempt_count
        if status == "passed" and attempt_count == 1:
            first_pass += 1
        failure_counts.update(failures)
        graded.append(
            {
                "task_id": task_id,
                "status": status,
                "failures": failures,
                "naming_findings": naming_findings,
                "execution": execution,
            }
        )

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
        "evidence_overclaim_rate": rate(failure_counts, "evidence_overclaim", total),
        "gate_failure_rate": rate(failure_counts, "harness_violation", total),
        "unavailable_rate": (unavailable / total) if total else 0.0,
        "retry_count": max(0, attempts - total),
        "actual_behavior_count": actual_behavior_count,
        "actual_behavior_evidence_coverage": (
            sum(actual_behavior_coverage) / len(actual_behavior_coverage) if actual_behavior_coverage else 0.0
        ),
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
