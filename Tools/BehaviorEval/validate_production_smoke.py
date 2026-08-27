#!/usr/bin/env python3
"""Validate Phase 1.1 Production Smoke contracts and optional Baseline v1 promotion evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from run_behavior_eval import build_request, validate_request

ROOT = Path(__file__).resolve().parents[2]
SUITES = ROOT / "Tests" / "BehaviorEval" / "suites.yaml"
GOLDEN_CASES = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
PRODUCTION_CONTRACTS = ROOT / "Tests" / "BehaviorEval" / "production-smoke-contracts.yaml"
TASK_CONTRACTS = ROOT / ".ai" / "harness" / "task-contracts"
EXPECTED_CASES = {
    "GOLDEN-ARCH-001": "architecture",
    "GOLDEN-NAMING-001": "naming",
    "GOLDEN-MUTATION-001": "mutation",
    "GOLDEN-EVIDENCE-001": "evidence",
}
INFRASTRUCTURE_FAILURES = {
    "evaluator_contract_failure",
    "runtime_timeout",
    "runtime_protocol_failure",
    "unavailable_required_evidence",
    "task_fixture_invalid",
    "broken_eval",
    "unavailable_evidence",
}


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _validate_static_contract(errors: list[str]) -> None:
    suites = (_load_yaml(SUITES).get("suites", {}) or {})
    production = suites.get("production_smoke", {}) or {}
    golden = {
        str(case.get("id")): case
        for case in (_load_yaml(GOLDEN_CASES).get("cases", []) or [])
        if isinstance(case, dict) and case.get("id")
    }
    production_contracts = (_load_yaml(PRODUCTION_CONTRACTS).get("cases", {}) or {})

    if production.get("rollout") != "manual":
        errors.append("production_smoke rollout must be manual.")
    if production.get("blocking_candidate") is not False:
        errors.append("production_smoke must remain non-blocking before Baseline v1 promotion.")
    if production.get("production_execution_required") is not True:
        errors.append("production_smoke must require production execution identity.")
    if int(production.get("max_agent_attempts", 0)) != 1:
        errors.append("production_smoke must use exactly one Agent attempt.")

    cases = production.get("cases", []) or []
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASES):
        errors.append(f"production_smoke must contain exactly {len(EXPECTED_CASES)} cases.")
        cases = []

    seen: set[str] = set()
    for suite_case in cases:
        if not isinstance(suite_case, dict):
            errors.append("production_smoke case must be a mapping.")
            continue
        task_id = str(suite_case.get("golden_task_id") or "")
        seen.add(task_id)
        expected_focus = EXPECTED_CASES.get(task_id)
        if expected_focus is None:
            errors.append(f"Unexpected production smoke case: {task_id}")
            continue
        if expected_focus not in set(suite_case.get("focus", []) or []):
            errors.append(f"{task_id}: missing focus {expected_focus}.")
        if suite_case.get("mutation_mode") != "sandbox":
            errors.append(f"{task_id}: mutation_mode must be sandbox.")
        if int(suite_case.get("max_agent_attempts", 1)) != 1:
            errors.append(f"{task_id}: max_agent_attempts must equal one.")

        golden_case = golden.get(task_id)
        production_contract = production_contracts.get(task_id)
        if golden_case is None:
            errors.append(f"Unknown Golden Task: {task_id}")
            continue
        if not isinstance(production_contract, dict):
            errors.append(f"{task_id}: production smoke contract is missing.")
            continue
        if not str(production_contract.get("production_prompt") or "").strip():
            errors.append(f"{task_id}: production_prompt is required.")

        case_dir = ROOT / "Artifacts" / "BehaviorEval" / "production-smoke-contract" / "cases" / task_id
        try:
            request = build_request(
                "production-smoke-contract",
                "fixture-revision",
                golden_case,
                suite_case,
                case_dir,
                suite_id="production_smoke",
                production_contract=production_contract,
            )
            validate_request(request, suite_id="production_smoke")
            if "expectation" in request:
                errors.append(f"{task_id}: Golden expectation leaked into production request.")
            task = request.get("task", {}) or {}
            if not str(task.get("production_prompt") or "").strip():
                errors.append(f"{task_id}: request lost production_prompt.")
            if task_id == "GOLDEN-EVIDENCE-001":
                if str((request.get("execution", {}) or {}).get("work_kind") or "") != "verification":
                    errors.append("GOLDEN-EVIDENCE-001 must execute as verification, not implementation.")
                observed = request.get("observed_evidence", []) or []
                if not any(
                    isinstance(item, dict)
                    and item.get("gate") == "compile"
                    and item.get("status") == "passed"
                    for item in observed
                ):
                    errors.append("GOLDEN-EVIDENCE-001 requires trusted compile PASS observed_evidence.")
            if task_id == "GOLDEN-MUTATION-001":
                allowed = ((request.get("workspace", {}) or {}).get("allowed_paths", []) or [])
                if allowed != ["CameraDebugger.cs"]:
                    errors.append("GOLDEN-MUTATION-001: allowed_paths were not transferred into the request.")
        except Exception as exc:  # noqa: BLE001 - validator aggregates contract failures.
            errors.append(f"{task_id}: request contract failed: {exc}")

    missing = sorted(set(EXPECTED_CASES) - seen)
    if missing:
        errors.append(f"Missing production smoke cases: {missing}")


def _required_route_gates(route: str) -> set[str]:
    if not route:
        return set()
    path = TASK_CONTRACTS / f"{route}.yaml"
    contract = _load_yaml(path)
    if contract.get("id") != route:
        raise ValueError(f"Task Contract identity mismatch: {route}")
    return {str(item) for item in contract.get("required_quality_gates", []) or []}


def _validate_baseline_summary(summary_path: Path, errors: list[str]) -> None:
    summary = _load_json(summary_path)
    if summary.get("suite") != "production_smoke":
        errors.append("Baseline promotion requires a production_smoke summary.")
        return

    results = summary.get("results", []) or []
    if not isinstance(results, list) or len(results) != len(EXPECTED_CASES):
        errors.append("Baseline promotion requires exactly four Production Smoke results.")
        return

    by_id = {
        str(item.get("task_id") or ""): item
        for item in results
        if isinstance(item, dict)
    }
    if set(by_id) != set(EXPECTED_CASES):
        errors.append(f"Baseline result IDs mismatch: {sorted(by_id)}")

    metrics = summary.get("metrics", {}) or {}
    if int(metrics.get("agent_quality_denominator", 0)) != len(EXPECTED_CASES):
        errors.append("Baseline promotion requires all 4 cases to be actually observed.")
    for metric in (
        "runtime_timeout_rate",
        "runtime_protocol_failure_rate",
        "evaluator_contract_failure_rate",
        "task_fixture_invalid_rate",
        "unavailable_required_evidence_rate",
        "inconclusive_rate",
        "broken_eval_rate",
    ):
        if float(metrics.get(metric, 0.0)) != 0.0:
            errors.append(f"Baseline promotion requires {metric} == 0.")

    run_root = summary_path.resolve().parent
    for task_id in EXPECTED_CASES:
        result = by_id.get(task_id, {}) or {}
        if result.get("status") != "passed":
            errors.append(f"{task_id}: Baseline requires status=passed, got {result.get('status')}.")
        if result.get("observation_state") != "observed":
            errors.append(f"{task_id}: Baseline requires observation_state=observed.")
        failures = set(result.get("failures", []) or [])
        infra = sorted(failures & INFRASTRUCTURE_FAILURES)
        if infra:
            errors.append(f"{task_id}: infrastructure/evaluator failures present: {infra}")

        candidate_path = run_root / "cases" / task_id / "candidate-result.yaml"
        if not candidate_path.is_file():
            errors.append(f"{task_id}: candidate-result.yaml is missing.")
            continue
        candidate = _load_yaml(candidate_path)
        execution = candidate.get("execution", {}) or {}
        if execution.get("observation_state") != "observed":
            errors.append(f"{task_id}: candidate evidence was not observed.")
        failure_class = str(candidate.get("failure_class") or execution.get("failure_class") or "")
        if failure_class in INFRASTRUCTURE_FAILURES:
            errors.append(f"{task_id}: failure_class blocks Baseline promotion: {failure_class}")

        route = str(candidate.get("route") or "")
        if not route:
            errors.append(f"{task_id}: observed candidate must have a route.")
            continue
        try:
            required_gates = _required_route_gates(route)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{task_id}: could not resolve required gates for {route}: {exc}")
            continue
        gates = candidate.get("gates", {}) or {}
        missing_or_nonpass = sorted(gate for gate in required_gates if gates.get(gate) != "passed")
        if missing_or_nonpass:
            errors.append(f"{task_id}: required Gate evidence not PASS: {missing_or_nonpass}")

    run_manifest_path = run_root / "run-manifest.yaml"
    if run_manifest_path.is_file():
        manifest = _load_yaml(run_manifest_path)
        if manifest.get("actual_agent_executed") is not True:
            errors.append("Baseline promotion requires actual_agent_executed=true.")
        if int(manifest.get("case_count", 0)) != len(EXPECTED_CASES):
            errors.append("Baseline promotion requires a full four-case run, not a single-case run.")
        if manifest.get("selected_case") not in {None, "", "null"}:
            errors.append("Baseline promotion cannot use a --case filtered run.")
        if manifest.get("status") != "passed":
            errors.append("Baseline promotion requires run-manifest status=passed.")
    else:
        errors.append("Baseline promotion requires run-manifest.yaml.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Optional Artifacts/BehaviorEval/<run>/summary.json to validate for Baseline v1 promotion.",
    )
    args = parser.parse_args()

    errors: list[str] = []
    try:
        _validate_static_contract(errors)
        if args.summary is not None:
            _validate_baseline_summary(args.summary, errors)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        errors.append(str(exc))

    if errors:
        print("Production smoke validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    if args.summary is None:
        print("Production smoke contract validation passed: Phase 1.1 four-case contract is fail-closed.")
    else:
        print("Production smoke Baseline v1 promotion validation passed: 4/4 observed, required gates PASS, runtime/evaluator defects 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
