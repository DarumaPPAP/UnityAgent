#!/usr/bin/env python3
"""Validate the Real Actual Behavior production smoke contract without invoking a model."""

from __future__ import annotations

from pathlib import Path

import yaml

from run_behavior_eval import build_request, validate_request

ROOT = Path(__file__).resolve().parents[2]
SUITES = ROOT / "Tests" / "BehaviorEval" / "suites.yaml"
GOLDEN_CASES = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
EXPECTED_CASES = {
    "GOLDEN-ARCH-001": "architecture",
    "GOLDEN-NAMING-001": "naming",
    "GOLDEN-MUTATION-001": "mutation",
    "GOLDEN-EVIDENCE-001": "evidence",
}


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def main() -> int:
    errors: list[str] = []
    try:
        suites = (_load_yaml(SUITES).get("suites", {}) or {})
        production = suites.get("production_smoke", {}) or {}
        golden = {
            str(case.get("id")): case
            for case in (_load_yaml(GOLDEN_CASES).get("cases", []) or [])
            if isinstance(case, dict) and case.get("id")
        }
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Production smoke validation failed:\n- {exc}")
        return 1

    if production.get("rollout") != "manual":
        errors.append("production_smoke rollout must be manual.")
    if production.get("blocking_candidate") is not False:
        errors.append("production_smoke must remain non-blocking in Phase 1.")
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
        if golden_case is None:
            errors.append(f"Unknown Golden Task: {task_id}")
            continue
        case_dir = ROOT / "Artifacts" / "BehaviorEval" / "production-smoke-contract" / "cases" / task_id
        try:
            request = build_request(
                "production-smoke-contract",
                "fixture-revision",
                golden_case,
                suite_case,
                case_dir,
                suite_id="production_smoke",
            )
            validate_request(request, suite_id="production_smoke")
            if "expectation" in request:
                errors.append(f"{task_id}: Golden expectation leaked into production request.")
            if task_id == "GOLDEN-MUTATION-001":
                allowed = ((request.get("workspace", {}) or {}).get("allowed_paths", []) or [])
                if allowed != ["CameraDebugger.cs"]:
                    errors.append("GOLDEN-MUTATION-001: allowed_paths were not transferred into the request.")
        except Exception as exc:  # noqa: BLE001 - validator reports contract failures.
            errors.append(f"{task_id}: request contract failed: {exc}")

    missing = sorted(set(EXPECTED_CASES) - seen)
    if missing:
        errors.append(f"Missing production smoke cases: {missing}")

    if errors:
        print("Production smoke validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Production smoke validation passed: architecture/naming/mutation/evidence, one real Agent attempt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
