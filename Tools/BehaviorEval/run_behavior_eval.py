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

import yaml

from normalize_result import BehaviorEvidenceError, normalize_case_result

ROOT = Path(__file__).resolve().parents[2]
SUITES_PATH = ROOT / "Tests" / "BehaviorEval" / "suites.yaml"
CASES_PATH = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
GOLDEN_RUNNER = ROOT / "Tools" / "GoldenEval" / "run_golden_evals.py"
DEFAULT_ROOT = ROOT / "Artifacts" / "BehaviorEval"

EXIT_PASSED = 0
EXIT_REGRESSION = 10
EXIT_INCONCLUSIVE = 20
EXIT_BROKEN = 30


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


def build_request(
    run_id: str,
    unityagent_revision: str,
    golden_case: dict,
    suite_case: dict,
    case_dir: Path,
    *,
    suite_id: str,
) -> dict:
    request = {
        "schema_version": "1.0",
        "run_id": run_id,
        "golden_task_id": str(golden_case.get("id") or ""),
        "unityagent_revision": unityagent_revision,
        "task": golden_case.get("task", {}) or {},
        "execution": {
            "mode": str(suite_case.get("execution_mode") or ""),
            "profile": str(suite_case.get("execution_profile") or ""),
            "work_kind": str(suite_case.get("work_kind") or ""),
            "max_agent_attempts": int(suite_case.get("max_agent_attempts") or 1),
        },
        "workspace": {
            "fixture": str(suite_case.get("workspace_fixture") or ""),
            "mutation_mode": str(suite_case.get("mutation_mode") or ""),
        },
        "evidence": suite_case.get("evidence", {}) or {},
        "result_root": _relative_to_root(case_dir),
        "suite": suite_id,
    }
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

    execution = request.get("execution", {}) or {}
    attempts = int(execution.get("max_agent_attempts", 0))
    if attempts < 1:
        raise BehaviorRunError("max_agent_attempts must be at least 1.")
    if suite_id == "smoke" and attempts != 1:
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
        "applied_policies": [],
        "gates": {},
        "signals": [],
        "knowledge": [],
        "unresolved": [],
        "failure_types": ["broken_eval"],
        "outcome": "failed",
        "attempt_count": 1,
        "generated_artifacts": [],
        "execution": {
            "mode": "actual_behavior",
            "run_id": run_id,
            "evidence_provenance": {},
            "evidence_coverage": {"covered_invariants": 0, "total_invariants": 0, "rate": 0.0, "sources": []},
            "behavior_findings": [
                {"code": "BEHAVIOR_PROTOCOL_FAILURE", "severity": "error", "message": message}
            ],
        },
    }


def _behavior_status(graded: dict) -> str:
    failures = set(graded.get("failures", []) or [])
    if "broken_eval" in failures:
        return "broken_eval"
    non_unavailable = failures - {"unavailable_evidence"}
    if failures and not non_unavailable:
        return "inconclusive"
    if failures:
        return "regression"
    return "passed"


def _rate(items: list[dict], failure: str) -> float:
    return (sum(failure in set(item.get("failures", []) or []) for item in items) / len(items)) if items else 0.0


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
        results.append(
            {
                "task_id": task_id,
                "status": status,
                "failures": list(item.get("failures", []) or []),
                "naming_findings": list(item.get("naming_findings", []) or []),
                "evidence_coverage": ((candidate.get("execution", {}) or {}).get("evidence_coverage", {}) or {}),
                "behavior_findings": ((candidate.get("execution", {}) or {}).get("behavior_findings", []) or []),
            }
        )

    counts = {status: sum(item["status"] == status for item in results) for status in (
        "passed",
        "regression",
        "inconclusive",
        "broken_eval",
    )}
    total = len(results)
    coverage_rates = [
        float((item.get("evidence_coverage", {}) or {}).get("rate", 0.0))
        for item in results
    ]
    first_pass = sum(
        item["status"] == "passed" and int(candidate_by_id.get(item["task_id"], {}).get("attempt_count", 1)) == 1
        for item in results
    )

    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "suite": suite_id,
        "unityagent_revision": unityagent_revision,
        "execution_owner": "DarumaPPAP/Unity-Graph-Engineering",
        "status_counts": counts,
        "metrics": {
            "actual_behavior_pass_rate": (counts["passed"] / total) if total else 0.0,
            "actual_first_pass_rate": (first_pass / total) if total else 0.0,
            "critical_invariant_pass_rate": (counts["passed"] / total) if total else 0.0,
            "route_accuracy": 1.0 - _rate(results, "routing_miss"),
            "context_accuracy": 1.0 - _rate(results, "context_miss"),
            "policy_violation_rate": _rate(results, "policy_violation"),
            "mutation_violation_rate": _rate(results, "mutation_violation"),
            "evidence_overclaim_rate": _rate(results, "evidence_overclaim"),
            "naming_regression_rate": _category_rate(results, task_categories, "naming"),
            "architecture_regression_rate": _category_rate(results, task_categories, "architecture"),
            "artifact_evidence_coverage": (sum(coverage_rates) / len(coverage_rates)) if coverage_rates else 0.0,
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
        f"- policy_violation_rate: {metrics.get('policy_violation_rate', 0.0):.3f}",
        f"- mutation_violation_rate: {metrics.get('mutation_violation_rate', 0.0):.3f}",
        f"- evidence_overclaim_rate: {metrics.get('evidence_overclaim_rate', 0.0):.3f}",
        f"- artifact_evidence_coverage: {metrics.get('artifact_evidence_coverage', 0.0):.3f}",
        "",
        "## Cases",
        "",
    ]
    for item in summary.get("results", []) or []:
        failures = ", ".join(item.get("failures", []) or []) or "none"
        lines.append(f"- `{item.get('task_id')}`: **{item.get('status')}** — {failures}")
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
        revision = resolve_git_revision(args.unityagent_revision)
        run_id = args.run_id or make_run_id()
        run_root = _safe_run_root(run_id)
        run_root.mkdir(parents=True, exist_ok=True)
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
        task_categories[task_id] = str(golden_case.get("category") or "")
        case_dir = run_root / "cases" / task_id
        case_dir.mkdir(parents=True, exist_ok=True)

        try:
            request = build_request(run_id, revision, golden_case, suite_case, case_dir, suite_id=args.suite)
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
            yaml.safe_dump(candidate, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    if args.request_only:
        manifest = _request_only_manifest(run_id, args.suite, revision, len(suite_cases))
        (run_root / "run-manifest.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
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
        args.suite,
        run_id,
        revision,
        golden_summary,
        candidates,
        task_categories,
        duration,
    )
    (run_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary_markdown(run_root / "summary.md", summary)

    graded_by_id = {str(item.get("task_id")): item for item in golden_summary.get("results", []) or []}
    for task_id, item in graded_by_id.items():
        case_dir = run_root / "cases" / task_id
        if case_dir.is_dir():
            (case_dir / "grader-result.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
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
        "schema_version": "1.0",
        "run_id": run_id,
        "suite": args.suite,
        "unityagent_revision": revision,
        "execution_owner": "DarumaPPAP/Unity-Graph-Engineering",
        "status": final_status,
        "actual_agent_executed": True,
        "case_count": len(suite_cases),
        "duration_seconds": duration,
    }
    (run_root / "run-manifest.yaml").write_text(
        yaml.safe_dump(run_manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
