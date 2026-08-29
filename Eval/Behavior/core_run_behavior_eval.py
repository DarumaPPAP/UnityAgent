#!/usr/bin/env python3
"""Run Actual Behavior suites through an external Production Execution adapter."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from normalize_result import BehaviorEvidenceError, normalize_case_result

ROOT = Path(__file__).resolve().parents[2]
SUITES_PATH = ROOT / "Tests" / "BehaviorEval" / "suites.yaml"
CASES_PATH = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
PRODUCTION_CONTRACTS_PATH = ROOT / "Tests" / "BehaviorEval" / "production-smoke-contracts.yaml"
GOLDEN_RUNNER = ROOT / "Tools" / "GoldenEval" / "run_golden_evals.py"
DEFAULT_ROOT = ROOT / "Artifacts" / "BehaviorEval"

EXIT_PASSED = 0
EXIT_REGRESSION = 10
EXIT_INCONCLUSIVE = 20
EXIT_BROKEN = 30

INFRASTRUCTURE_FAILURES = {
    "evaluator_contract_failure",
    "runtime_timeout",
    "runtime_protocol_failure",
    "unavailable_required_evidence",
    "task_fixture_invalid",
}


class BehaviorRunError(ValueError):
    """Behavior Eval request or protocol setup is invalid."""


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise BehaviorRunError(f"Expected mapping: {path}")
    return data


def resolve_git_revision(override: str | None = None) -> str:
    if override:
        return override
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    revision = completed.stdout.strip() if completed.returncode == 0 else ""
    if not revision:
        raise BehaviorRunError("UnityAgent revision could not be resolved; pass --unityagent-revision explicitly.")
    return revision


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("behavior-%Y%m%d-%H%M%S")


def _relative_to_root(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _safe_run_root(run_id: str) -> Path:
    if not run_id or any(part in {"..", "."} for part in Path(run_id).parts) or "/" in run_id or "\\" in run_id:
        raise BehaviorRunError(f"Invalid run_id: {run_id}")
    root = (DEFAULT_ROOT / run_id).resolve()
    root.relative_to(DEFAULT_ROOT.resolve())
    return root


def _create_fresh_run_root(run_root: Path) -> None:
    if run_root.exists():
        raise BehaviorRunError(
            f"Behavior Eval run output is immutable and already exists: {_relative_to_root(run_root)}"
        )
    run_root.mkdir(parents=True, exist_ok=False)


def _scope_paths(suite_case: dict, key: str) -> list[str]:
    raw = suite_case.get(key, []) or []
    if not isinstance(raw, list):
        raise BehaviorRunError(f"{key} must be a list.")
    values: list[str] = []
    for item in raw:
        value = str(item or "").strip().replace("\\", "/")
        path = Path(value)
        if not value or path.is_absolute() or ".." in path.parts:
            raise BehaviorRunError(f"{key} entries must be non-empty repository-relative paths without traversal: {item}")
        values.append(value)
    return values


def _production_contracts() -> dict[str, dict[str, Any]]:
    if not PRODUCTION_CONTRACTS_PATH.is_file():
        return {}
    doc = load_yaml(PRODUCTION_CONTRACTS_PATH)
    cases = doc.get("cases", {}) or {}
    if not isinstance(cases, dict):
        raise BehaviorRunError("production-smoke-contracts.yaml cases must be a mapping.")
    return {str(key): value for key, value in cases.items() if isinstance(value, dict)}


def _task_payload(golden_case: dict, production_contract: dict | None) -> dict:
    golden_task = golden_case.get("task", {}) or {}
    if not production_contract:
        return golden_task
    production_prompt = str(production_contract.get("production_prompt") or "").strip()
    if not production_prompt:
        raise BehaviorRunError(f"{golden_case.get('id')}: production_prompt is required for production_smoke.")
    return {
        "summary": str(golden_task.get("summary") or ""),
        "production_prompt": production_prompt,
    }


def build_request(
    run_id: str,
    unityagent_revision: str,
    golden_case: dict,
    suite_case: dict,
    case_dir: Path,
    *,
    suite_id: str,
    production_contract: dict | None = None,
) -> dict:
    workspace = {
        "fixture": str(suite_case.get("workspace_fixture") or ""),
        "mutation_mode": str(suite_case.get("mutation_mode") or ""),
    }
    allowed_paths = _scope_paths(suite_case, "allowed_paths")
    prohibited_paths = _scope_paths(suite_case, "prohibited_paths")
    if allowed_paths:
        workspace["allowed_paths"] = allowed_paths
    if prohibited_paths:
        workspace["prohibited_paths"] = prohibited_paths

    request = {
        "schema_version": "1.0",
        "run_id": run_id,
        "golden_task_id": str(golden_case.get("id") or ""),
        "unityagent_revision": unityagent_revision,
        "task": _task_payload(golden_case, production_contract),
        "execution": {
            "mode": str(suite_case.get("execution_mode") or ""),
            "profile": str(suite_case.get("execution_profile") or ""),
            "work_kind": str(suite_case.get("work_kind") or ""),
            "max_agent_attempts": int(suite_case.get("max_agent_attempts") or 1),
        },
        "workspace": workspace,
        "evidence": suite_case.get("evidence", {}) or {},
        "result_root": _relative_to_root(case_dir),
        "suite": suite_id,
    }
    if production_contract:
        request["primary_focus"] = str(production_contract.get("primary_focus") or "")
        observed = production_contract.get("observed_evidence", []) or []
        if observed:
            request["observed_evidence"] = observed
    validate_request(request, suite_id=suite_id)
    return request


def validate_request(request: dict, *, suite_id: str) -> None:
    required = {
        "schema_version",
        "run_id",
        "golden_task_id",
        "unityagent_revision",
        "task",
        "execution",
        "workspace",
        "evidence",
        "result_root",
    }
    missing = sorted(required - set(request))
    if missing:
        raise BehaviorRunError(f"Behavior Eval Request missing fields: {missing}")
    if request.get("schema_version") != "1.0":
        raise BehaviorRunError("Behavior Eval Request schema_version must be 1.0.")
    if "expectation" in request:
        raise BehaviorRunError("Golden expectation must never be sent to the executor.")

    task = request.get("task", {}) or {}
    if not isinstance(task, dict):
        raise BehaviorRunError("task must be a mapping.")
    forbidden_task_keys = {"expected_route", "required_signals", "forbidden_signals", "required_policies", "required_gates"}
    leaked = sorted(forbidden_task_keys & set(task))
    if leaked:
        raise BehaviorRunError(f"Golden expectation-like fields are forbidden in production task: {leaked}")
    if suite_id == "production_smoke" and not str(task.get("production_prompt") or "").strip():
        raise BehaviorRunError("production_smoke requires task.production_prompt.")

    execution = request.get("execution", {}) or {}
    attempts = int(execution.get("max_agent_attempts", 0))
    if attempts < 1:
        raise BehaviorRunError("max_agent_attempts must be at least 1.")
    if suite_id in {"smoke", "production_smoke"} and attempts != 1:
        raise BehaviorRunError("Smoke Actual Behavior Eval must use exactly one Agent attempt.")

    workspace = request.get("workspace", {}) or {}
    if workspace.get("mutation_mode") != "sandbox":
        raise BehaviorRunError("Actual Behavior workspace mutation_mode must be sandbox.")
    fixture = Path(str(workspace.get("fixture") or ""))
    if fixture.is_absolute() or ".." in fixture.parts:
        raise BehaviorRunError("Behavior fixture must be a repository-relative path without traversal.")
    fixture_path = (ROOT / fixture).resolve()
    fixture_root = (ROOT / "Tests" / "BehaviorEval" / "Fixtures").resolve()
    try:
        fixture_path.relative_to(fixture_root)
    except ValueError as exc:
        raise BehaviorRunError(f"Behavior fixture is outside the Fixture root: {fixture}") from exc
    if not fixture_path.exists():
        raise BehaviorRunError(f"Behavior fixture does not exist: {fixture}")

    for key in ("allowed_paths", "prohibited_paths"):
        raw = workspace.get(key, []) or []
        if not isinstance(raw, list):
            raise BehaviorRunError(f"workspace.{key} must be a list.")
        for item in raw:
            value = str(item or "").strip()
            path = Path(value)
            if not value or path.is_absolute() or ".." in path.parts:
                raise BehaviorRunError(
                    f"workspace.{key} entries must be non-empty repository-relative paths without traversal: {item}"
                )

    observed = request.get("observed_evidence", []) or []
    if not isinstance(observed, list):
        raise BehaviorRunError("observed_evidence must be a list.")
    for item in observed:
        if not isinstance(item, dict):
            raise BehaviorRunError("observed_evidence entries must be mappings.")
        for key in ("id", "gate", "status", "source"):
            if not str(item.get(key) or "").strip():
                raise BehaviorRunError(f"observed_evidence entry missing {key}.")
        if item.get("status") not in {"passed", "failed", "unavailable"}:
            raise BehaviorRunError("observed_evidence.status must be passed/failed/unavailable.")

    result_root = Path(str(request.get("result_root") or ""))
    if result_root.is_absolute() or ".." in result_root.parts:
        raise BehaviorRunError("result_root must be repository-relative without traversal.")
    resolved_result = (ROOT / result_root).resolve()
    try:
        resolved_result.relative_to(DEFAULT_ROOT.resolve())
    except ValueError as exc:
        raise BehaviorRunError("result_root must be under Artifacts/BehaviorEval.") from exc


def build_executor_command(base_command: list[str], request_path: Path, case_dir: Path) -> list[str]:
    if not base_command:
        raise BehaviorRunError("External executor command is empty.")
    return [*base_command, "--request", str(request_path), "--output", str(case_dir)]


def _load_suite(suite_id: str) -> tuple[dict, list[dict], dict[str, dict]]:
    suites = load_yaml(SUITES_PATH).get("suites", {}) or {}
    suite = suites.get(suite_id)
    if not isinstance(suite, dict):
        raise BehaviorRunError(f"Unknown Behavior Eval suite: {suite_id}")
    suite_cases = suite.get("cases", []) or []
    if not isinstance(suite_cases, list):
        raise BehaviorRunError(f"Behavior Eval suite {suite_id} cases must be a list.")

    golden_doc = load_yaml(CASES_PATH)
    golden_cases = {
        str(case.get("id")): case
        for case in golden_doc.get("cases", []) or []
        if isinstance(case, dict) and case.get("id")
    }
    return suite, suite_cases, golden_cases


def _broken_candidate(task_id: str, run_id: str, message: str) -> dict:
    return {
        "task_id": task_id,
        "route": "",
        "fingerprint": None,
        "applied_policies": [],
        "gates": {},
        "signals": [],
        "knowledge": [],
        "unresolved": [],
        "failure_types": ["evaluator_contract_failure"],
        "failure_class": "evaluator_contract_failure",
        "outcome": "failed",
        "attempt_count": 1,
        "generated_artifacts": [],
        "execution": {
            "mode": "actual_behavior",
            "run_id": run_id,
            "observation_state": "not_observed",
            "failure_class": "evaluator_contract_failure",
            "evidence_provenance": {},
            "evidence_coverage": {"covered_invariants": 0, "total_invariants": 0, "rate": 0.0, "sources": []},
            "behavior_findings": [
                {"code": "BEHAVIOR_PROTOCOL_FAILURE", "severity": "error", "message": message}
            ],
        },
    }


def _failure_set(graded: dict) -> set[str]:
    return set(graded.get("failures", []) or [])


def _behavior_status(graded: dict) -> str:
    failures = _failure_set(graded)
    if "broken_eval" in failures or "evaluator_contract_failure" in failures:
        return "broken_eval" if "broken_eval" in failures else "inconclusive"
    if failures & INFRASTRUCTURE_FAILURES:
        return "inconclusive"
    non_unavailable = failures - {"unavailable_evidence"}
    if failures and not non_unavailable:
        return "inconclusive"
    if failures:
        return "regression"
    return "passed"


def _rate(items: list[dict], failure: str) -> float:
    return (sum(failure in _failure_set(item) for item in items) / len(items)) if items else 0.0


def _category_rate(items: list[dict], task_categories: dict[str, str], category: str) -> float:
    selected = [item for item in items if task_categories.get(str(item.get("task_id"))) == category]
    if not selected:
        return 0.0
    failed = sum(_behavior_status(item) != "passed" for item in selected)
    return failed / len(selected)


def build_behavior_summary(
    suite_id: str,
    run_id: str,
    unityagent_revision: str,
    golden_summary: dict,
    candidates: list[dict],
    task_categories: dict[str, str],
    duration: float,
) -> dict:
    graded = list(golden_summary.get("results", []) or [])
    candidate_by_id = {str(item.get("task_id")): item for item in candidates}
    results: list[dict] = []

    for item in graded:
        task_id = str(item.get("task_id") or "")
        candidate = candidate_by_id.get(task_id, {})
        status = _behavior_status(item)
        execution = candidate.get("execution", {}) or {}
        results.append(
            {
                "task_id": task_id,
                "status": status,
                "failures": list(item.get("failures", []) or []),
                "failure_class": str(candidate.get("failure_class") or execution.get("failure_class") or ""),
                "observation_state": str(execution.get("observation_state") or "observed"),
                "naming_findings": list(item.get("naming_findings", []) or []),
                "evidence_coverage": execution.get("evidence_coverage", {}) or {},
                "behavior_findings": execution.get("behavior_findings", []) or [],
            }
        )

    counts = {status: sum(item["status"] == status for item in results) for status in (
        "passed", "regression", "inconclusive", "broken_eval"
    )}
    total = len(results)
    observed = [item for item in results if item.get("observation_state") == "observed"]
    observed_count = len(observed)
    coverage_rates = [float((item.get("evidence_coverage", {}) or {}).get("rate", 0.0)) for item in observed]
    first_pass = sum(
        item["status"] == "passed" and int(candidate_by_id.get(item["task_id"], {}).get("attempt_count", 1)) == 1
        for item in observed
    )
    observed_regressions = sum(item["status"] == "regression" for item in observed)

    return {
        "schema_version": "1.1",
        "run_id": run_id,
        "suite": suite_id,
        "unityagent_revision": unityagent_revision,
        "execution_owner": "DarumaPPAP/Unity-Graph-Engineering",
        "status_counts": counts,
        "metrics": {
            "actual_behavior_pass_rate": (counts["passed"] / total) if total else 0.0,
            "agent_quality_denominator": observed_count,
            "actual_first_pass_rate": (first_pass / observed_count) if observed_count else 0.0,
            "agent_behavior_regression_rate": (observed_regressions / observed_count) if observed_count else 0.0,
            "route_accuracy": 1.0 - _rate(observed, "routing_miss") if observed else 0.0,
            "context_accuracy": 1.0 - _rate(observed, "context_miss") if observed else 0.0,
            "policy_violation_rate": _rate(observed, "policy_violation"),
            "mutation_violation_rate": _rate(observed, "mutation_violation"),
            "evidence_overclaim_rate": _rate(observed, "evidence_overclaim"),
            "naming_regression_rate": _category_rate(observed, task_categories, "naming"),
            "architecture_regression_rate": _category_rate(observed, task_categories, "architecture"),
            "artifact_evidence_coverage": (sum(coverage_rates) / len(coverage_rates)) if coverage_rates else 0.0,
            "runtime_timeout_rate": _rate(results, "runtime_timeout"),
            "runtime_protocol_failure_rate": _rate(results, "runtime_protocol_failure"),
            "evaluator_contract_failure_rate": _rate(results, "evaluator_contract_failure"),
            "task_fixture_invalid_rate": _rate(results, "task_fixture_invalid"),
            "unavailable_required_evidence_rate": _rate(results, "unavailable_required_evidence"),
            "inconclusive_rate": (counts["inconclusive"] / total) if total else 0.0,
            "broken_eval_rate": (counts["broken_eval"] / total) if total else 0.0,
            "execution_duration": duration,
        },
        "results": results,
    }


def write_summary_markdown(path: Path, summary: dict) -> None:
    counts = summary.get("status_counts", {}) or {}
    metrics = summary.get("metrics", {}) or {}
    lines = [
        "# Actual Behavior Eval",
        "",
        f"- Suite: `{summary.get('suite')}`",
        f"- UnityAgent: `{summary.get('unityagent_revision')}`",
        f"- Execution Owner: `{summary.get('execution_owner')}`",
        "",
        f"PASS: {counts.get('passed', 0)}",
        f"Regression: {counts.get('regression', 0)}",
        f"Inconclusive: {counts.get('inconclusive', 0)}",
        f"Broken Eval: {counts.get('broken_eval', 0)}",
        "",
        "## Critical Metrics",
        "",
        f"- agent_quality_denominator: {metrics.get('agent_quality_denominator', 0)}",
        f"- policy_violation_rate: {metrics.get('policy_violation_rate', 0.0):.3f}",
        f"- mutation_violation_rate: {metrics.get('mutation_violation_rate', 0.0):.3f}",
        f"- evidence_overclaim_rate: {metrics.get('evidence_overclaim_rate', 0.0):.3f}",
        f"- runtime_timeout_rate: {metrics.get('runtime_timeout_rate', 0.0):.3f}",
        f"- evaluator_contract_failure_rate: {metrics.get('evaluator_contract_failure_rate', 0.0):.3f}",
        "",
        "## Cases",
        "",
    ]
    for item in summary.get("results", []) or []:
        failures = ", ".join(item.get("failures", []) or []) or "none"
        lines.append(
            f"- `{item.get('task_id')}`: **{item.get('status')}** "
            f"(observation={item.get('observation_state')}) — {failures}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _request_only_manifest(run_id: str, suite_id: str, revision: str, count: int) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "suite": suite_id,
        "unityagent_revision": revision,
        "execution_owner": "DarumaPPAP/Unity-Graph-Engineering",
        "status": "requests_only",
        "actual_agent_executed": False,
        "case_count": count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="smoke")
    parser.add_argument("--run-id")
    parser.add_argument("--unityagent-revision")
    parser.add_argument("--case", "--only-case", dest="only_case", default=None)
    parser.add_argument("--request-only", action="store_true")
    parser.add_argument(
        "--executor-command",
        nargs=argparse.REMAINDER,
        help="External adapter command as argument list. The runner appends --request PATH --output CASE_DIR.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    try:
        suite, suite_cases, golden_cases = _load_suite(args.suite)
        if args.only_case:
            suite_cases = [
                item for item in suite_cases
                if isinstance(item, dict) and str(item.get("golden_task_id") or "") == args.only_case
            ]
            if not suite_cases:
                raise BehaviorRunError(f"Case {args.only_case} is not part of suite {args.suite}.")
        production_contracts = _production_contracts() if args.suite == "production_smoke" else {}
        revision = resolve_git_revision(args.unityagent_revision)
        run_id = args.run_id or make_run_id()
        run_root = _safe_run_root(run_id)
        _create_fresh_run_root(run_root)
    except (OSError, yaml.YAMLError, BehaviorRunError, ValueError) as exc:
        print(f"Behavior Eval setup failed: {exc}")
        return EXIT_BROKEN

    candidates: list[dict] = []
    task_categories: dict[str, str] = {}

    for suite_case in suite_cases:
        if not isinstance(suite_case, dict):
            print("Behavior Eval suite contains a non-mapping case.")
            return EXIT_BROKEN
        task_id = str(suite_case.get("golden_task_id") or "")
        golden_case = golden_cases.get(task_id)
        if golden_case is None:
            print(f"Behavior Eval suite references unknown Golden Task: {task_id}")
            return EXIT_BROKEN
        production_contract = production_contracts.get(task_id) if args.suite == "production_smoke" else None
        if args.suite == "production_smoke" and production_contract is None:
            print(f"{task_id}: production smoke contract is missing.")
            return EXIT_BROKEN
        task_categories[task_id] = str(golden_case.get("category") or "")
        case_dir = run_root / "cases" / task_id
        case_dir.mkdir(parents=True, exist_ok=False)

        try:
            request = build_request(
                run_id,
                revision,
                golden_case,
                suite_case,
                case_dir,
                suite_id=args.suite,
                production_contract=production_contract,
            )
        except (BehaviorRunError, ValueError) as exc:
            print(f"{task_id}: request build failed: {exc}")
            return EXIT_BROKEN
        request_path = case_dir / "request.yaml"
        request_path.write_text(yaml.safe_dump(request, sort_keys=False, allow_unicode=True), encoding="utf-8")

        if args.request_only:
            continue
        if not args.executor_command:
            print("Actual Behavior execution requires --executor-command or --request-only.")
            return EXIT_BROKEN

        command = build_executor_command(list(args.executor_command), request_path, case_dir)
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0 and not (case_dir / "execution-envelope.yaml").is_file():
            candidate = _broken_candidate(
                task_id,
                run_id,
                f"External executor returned {completed.returncode} without an execution envelope.",
            )
        else:
            try:
                candidate = normalize_case_result(case_dir, golden_case, suite_case)
            except (OSError, UnicodeError, yaml.YAMLError, BehaviorEvidenceError, ValueError) as exc:
                candidate = _broken_candidate(task_id, run_id, str(exc))

        candidates.append(candidate)
        (case_dir / "candidate-result.yaml").write_text(
            yaml.safe_dump(candidate, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

    if args.request_only:
        manifest = _request_only_manifest(run_id, args.suite, revision, len(suite_cases))
        (run_root / "run-manifest.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        print(
            f"Behavior Eval request bundle generated: {len(suite_cases)} case(s). "
            "No Agent or model execution was performed."
        )
        return EXIT_PASSED

    candidate_doc = {"schema_version": "1.0", "results": candidates}
    candidate_path = run_root / "candidate-results.yaml"
    candidate_path.write_text(yaml.safe_dump(candidate_doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    golden_output = run_root / "golden-summary.json"

    completed = subprocess.run(
        [sys.executable, str(GOLDEN_RUNNER), "--results", str(candidate_path), "--output", str(golden_output)],
        cwd=ROOT,
        check=False,
    )
    if not golden_output.is_file():
        print(f"Existing Golden Runner did not produce a summary (exit={completed.returncode}).")
        return EXIT_BROKEN

    golden_summary = json.loads(golden_output.read_text(encoding="utf-8"))
    duration = time.perf_counter() - started
    summary = build_behavior_summary(
        args.suite, run_id, revision, golden_summary, candidates, task_categories, duration
    )
    (run_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary_markdown(run_root / "summary.md", summary)

    graded_by_id = {str(item.get("task_id")): item for item in golden_summary.get("results", []) or []}
    for task_id, item in graded_by_id.items():
        case_dir = run_root / "cases" / task_id
        if case_dir.is_dir():
            (case_dir / "grader-result.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    counts = summary.get("status_counts", {}) or {}
    final_status = "passed"
    if counts.get("broken_eval", 0):
        exit_code = EXIT_BROKEN
        final_status = "broken_eval"
    elif counts.get("regression", 0):
        exit_code = EXIT_REGRESSION
        final_status = "regression"
    elif counts.get("inconclusive", 0):
        exit_code = EXIT_INCONCLUSIVE
        final_status = "inconclusive"
    else:
        exit_code = EXIT_PASSED

    run_manifest = {
        "schema_version": "1.1",
        "run_id": run_id,
        "suite": args.suite,
        "unityagent_revision": revision,
        "execution_owner": "DarumaPPAP/Unity-Graph-Engineering",
        "status": final_status,
        "actual_agent_executed": True,
        "case_count": len(suite_cases),
        "selected_case": args.only_case,
        "duration_seconds": duration,
        "baseline_candidate": False if final_status != "passed" else args.suite == "production_smoke" and len(suite_cases) == 4,
    }
    (run_root / "run-manifest.yaml").write_text(
        yaml.safe_dump(run_manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
