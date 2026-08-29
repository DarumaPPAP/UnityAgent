#!/usr/bin/env python3
"""Grade already-observed Actual Behavior candidate results.

This canonical Phase-6 entrypoint never launches Runtime, Codex, Unity, or an
external adapter. Production execution happens first through Runtime; Eval
consumes the resulting facts/artifacts afterward.

The request helpers in this module only construct/validate the execution
contract. They never invoke the command they format.
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
from Eval.Datasets.paths import canonicalize_repo_path  # noqa: E402

CASES_PATH = ROOT / "Eval" / "Datasets" / "Golden" / "cases.yaml"
BEHAVIOR_DATASET_ROOT = ROOT / "Eval" / "Datasets" / "Behavior"
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


def _scope_paths(suite_case: dict[str, Any], key: str) -> list[str]:
    raw = suite_case.get(key, []) or []
    if not isinstance(raw, list):
        raise BehaviorEvalError(f"{key} must be a list")
    values: list[str] = []
    for item in raw:
        value = str(item or "").strip().replace("\\", "/")
        path = Path(value)
        if not value or path.is_absolute() or ".." in path.parts:
            raise BehaviorEvalError(f"{key} entries must be safe repository-relative paths: {item}")
        values.append(value)
    return values


def _task_payload(golden_case: dict[str, Any], production_contract: dict[str, Any] | None) -> dict[str, Any]:
    task = golden_case.get("task") or {}
    if not isinstance(task, dict):
        raise BehaviorEvalError("Golden task must be a mapping")
    if not production_contract:
        return dict(task)
    prompt = str(production_contract.get("production_prompt") or "").strip()
    if not prompt:
        raise BehaviorEvalError("production_prompt is required for production_smoke")
    return {"summary": str(task.get("summary") or ""), "production_prompt": prompt}


def build_request(
    run_id: str,
    unityagent_revision: str,
    golden_case: dict[str, Any],
    suite_case: dict[str, Any],
    case_dir: Path,
    *,
    suite_id: str,
    production_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Runtime request without embedding Golden expectations."""
    fixture = canonicalize_repo_path(str(suite_case.get("workspace_fixture") or ""))
    workspace: dict[str, Any] = {
        "fixture": fixture,
        "mutation_mode": str(suite_case.get("mutation_mode") or ""),
    }
    allowed = _scope_paths(suite_case, "allowed_paths")
    prohibited = _scope_paths(suite_case, "prohibited_paths")
    if allowed:
        workspace["allowed_paths"] = allowed
    if prohibited:
        workspace["prohibited_paths"] = prohibited

    try:
        result_root = case_dir.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise BehaviorEvalError("case_dir must be inside the repository") from exc

    request: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": str(run_id),
        "golden_task_id": str(golden_case.get("id") or ""),
        "unityagent_revision": str(unityagent_revision),
        "task": _task_payload(golden_case, production_contract),
        "execution": {
            "mode": str(suite_case.get("execution_mode") or ""),
            "profile": str(suite_case.get("execution_profile") or ""),
            "work_kind": str(suite_case.get("work_kind") or ""),
            "max_agent_attempts": int(suite_case.get("max_agent_attempts") or 1),
        },
        "workspace": workspace,
        "evidence": suite_case.get("evidence") or {},
        "result_root": result_root,
        "suite": suite_id,
    }
    if production_contract:
        request["primary_focus"] = str(production_contract.get("primary_focus") or "")
        observed = production_contract.get("observed_evidence", []) or []
        if observed:
            request["observed_evidence"] = observed
    validate_request(request, suite_id=suite_id)
    return request


def validate_request(request: dict[str, Any], *, suite_id: str) -> None:
    required = {
        "schema_version", "run_id", "golden_task_id", "unityagent_revision",
        "task", "execution", "workspace", "evidence", "result_root",
    }
    missing = sorted(required - set(request))
    if missing:
        raise BehaviorEvalError(f"Behavior Eval Request missing fields: {missing}")
    if request.get("schema_version") != "1.0":
        raise BehaviorEvalError("Behavior Eval Request schema_version must be 1.0")
    if "expectation" in request:
        raise BehaviorEvalError("Golden expectation must never be sent to Runtime")

    task = request.get("task") or {}
    if not isinstance(task, dict):
        raise BehaviorEvalError("task must be a mapping")
    expectation_keys = {
        "expectation", "expected_result", "invariants", "expected_trajectory",
        "forbidden", "evidence_requirements", "expected_route", "required_signals",
        "forbidden_signals", "required_policies", "required_gates",
    }
    leaked = sorted(expectation_keys & set(task))
    if leaked:
        raise BehaviorEvalError(f"Golden expectation-like fields are forbidden in Runtime task: {leaked}")
    if suite_id == "production_smoke" and not str(task.get("production_prompt") or "").strip():
        raise BehaviorEvalError("production_smoke requires task.production_prompt")

    execution = request.get("execution") or {}
    attempts = int(execution.get("max_agent_attempts", 0))
    if attempts < 1:
        raise BehaviorEvalError("max_agent_attempts must be at least 1")
    if suite_id in {"smoke", "production_smoke"} and attempts != 1:
        raise BehaviorEvalError("smoke suites must use exactly one Agent attempt")

    workspace = request.get("workspace") or {}
    if not isinstance(workspace, dict) or workspace.get("mutation_mode") != "sandbox":
        raise BehaviorEvalError("Actual Behavior workspace mutation_mode must be sandbox")
    fixture = Path(str(workspace.get("fixture") or ""))
    if fixture.is_absolute() or ".." in fixture.parts:
        raise BehaviorEvalError("Behavior fixture must be repository-relative without traversal")
    fixture_path = (ROOT / fixture).resolve()
    canonical_fixture_root = (BEHAVIOR_DATASET_ROOT / "Fixtures").resolve()
    legacy_fixture_root = (ROOT / "Tests" / "BehaviorEval" / "Fixtures").resolve()
    if not any(fixture_path == root or root in fixture_path.parents for root in (canonical_fixture_root, legacy_fixture_root)):
        raise BehaviorEvalError(f"Behavior fixture is outside approved fixture roots: {fixture}")
    if not fixture_path.exists():
        raise BehaviorEvalError(f"Behavior fixture does not exist: {fixture}")

    for key in ("allowed_paths", "prohibited_paths"):
        for item in workspace.get(key, []) or []:
            value = str(item or "").strip()
            path = Path(value)
            if not value or path.is_absolute() or ".." in path.parts:
                raise BehaviorEvalError(f"workspace.{key} contains unsafe path: {item}")

    observed = request.get("observed_evidence", []) or []
    if not isinstance(observed, list):
        raise BehaviorEvalError("observed_evidence must be a list")
    for item in observed:
        if not isinstance(item, dict):
            raise BehaviorEvalError("observed_evidence entries must be mappings")
        for key in ("id", "gate", "status", "source"):
            if not str(item.get(key) or "").strip():
                raise BehaviorEvalError(f"observed_evidence entry missing {key}")
        if item.get("status") not in {"passed", "failed", "unavailable"}:
            raise BehaviorEvalError("observed_evidence.status must be passed/failed/unavailable")


def build_executor_command(base_command: list[str], request_path: Path, output_path: Path) -> list[str]:
    """Compatibility-only protocol formatting. This function never executes it."""
    if not base_command or any(not isinstance(item, str) or not item for item in base_command):
        raise BehaviorEvalError("base_command must contain non-empty string arguments")
    return [*base_command, "--request", str(request_path), "--output", str(output_path)]


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
