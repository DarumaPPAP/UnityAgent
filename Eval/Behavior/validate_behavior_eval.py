#!/usr/bin/env python3
"""Validate canonical Actual Behavior Eval boundaries without execution."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from run_behavior_eval import build_executor_command, build_request, validate_request

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "Eval" / "Behavior" / "behavior-eval-contract.yaml"
REQUEST_SCHEMA = ROOT / "Eval" / "Datasets" / "Behavior" / "behavior-eval-request.schema.yaml"
ENVELOPE_SCHEMA = ROOT / "Eval" / "Datasets" / "Behavior" / "execution-envelope.schema.yaml"
SUITES = ROOT / "Eval" / "Datasets" / "Behavior" / "suites.yaml"
PRODUCTION_CONTRACTS = ROOT / "Eval" / "Datasets" / "Behavior" / "production-smoke-contracts.yaml"
GOLDEN_CASES = ROOT / "Eval" / "Datasets" / "Golden" / "cases.yaml"
CANDIDATE_SCHEMA = ROOT / "Eval" / "Datasets" / "Golden" / "candidate-result.schema.yaml"
CANONICAL_RUNNER = ROOT / "Eval" / "Behavior" / "run_behavior_eval.py"
RUNTIME_ADAPTER = ROOT / "Eval" / "Behavior" / "runtime_adapter.py"
REMOVED_COMPATIBILITY_ROOT = ROOT / "Eval" / "Compatibility"


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []
    try:
        contract = load_yaml(CONTRACT)
        request_schema = load_yaml(REQUEST_SCHEMA)
        envelope_schema = load_yaml(ENVELOPE_SCHEMA)
        suites = load_yaml(SUITES)
        production_contracts = load_yaml(PRODUCTION_CONTRACTS).get("cases", {}) or {}
        cases = {
            str(case.get("id")): case
            for case in load_yaml(GOLDEN_CASES).get("cases", []) or []
            if isinstance(case, dict) and case.get("id")
        }
        candidate_schema = load_yaml(CANDIDATE_SCHEMA)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Behavior Eval validation failed:\n- {exc}")
        return 1

    ownership = contract.get("ownership", {}) or {}
    require(ownership.get("behavior_and_grading") == "DarumaPPAP/UnityAgent:Eval", "Eval grading ownership is not canonical.", errors)
    require(ownership.get("execution_runtime") == "DarumaPPAP/UnityAgent:Runtime", "Runtime execution ownership is not canonical.", errors)
    require(ownership.get("durable_evidence") == "DarumaPPAP/UnityAgent:Persistence", "Persistence Evidence ownership is not canonical.", errors)

    rules = contract.get("rules", {}) or {}
    for rule in (
        "production_execution_path_required",
        "evaluation_specific_agent_behavior_forbidden",
        "actual_behavior_requires_execution_evidence",
        "one_agent_attempt_for_smoke",
        "unavailable_is_not_passed",
        "mutation_requires_sandbox",
        "eval_runtime_execution_forbidden",
        "golden_expectation_in_runtime_prompt_forbidden",
        "structured_runtime_facts_must_be_preserved",
        "not_observed_quality_denominator_forbidden",
        "change_proposal_must_not_apply",
    ):
        require(rules.get(rule) is True, f"canonical Behavior contract missing true rule: {rule}", errors)

    require(request_schema.get("schema_version") == "1.1", "Behavior request schema parity drifted.", errors)
    require(envelope_schema.get("schema_version") == "1.1", "Execution envelope schema parity drifted.", errors)
    require(candidate_schema.get("schema_version") == "1.3", "Candidate result schema parity drifted.", errors)

    suite_map = suites.get("suites", {}) or {}
    smoke = suite_map.get("smoke", {}) or {}
    smoke_cases = smoke.get("cases", []) or []
    require(8 <= len(smoke_cases) <= 12, f"Smoke suite must contain 8-12 cases; found {len(smoke_cases)}.", errors)
    require(int(smoke.get("max_agent_attempts", 0)) == 1, "Smoke suite must use one Agent attempt.", errors)
    focuses: Counter[str] = Counter()
    for item in smoke_cases:
        if not isinstance(item, dict):
            errors.append("Smoke suite case must be a mapping.")
            continue
        task_id = str(item.get("golden_task_id") or "")
        require(task_id in cases, f"Unknown Golden Task in smoke suite: {task_id}", errors)
        focuses.update(str(value) for value in item.get("focus", []) or [])
        if task_id not in cases:
            continue
        case_dir = ROOT / "Artifacts" / "BehaviorEval" / "phase8-protocol" / task_id
        try:
            request = build_request("phase8-protocol", "revision", cases[task_id], item, case_dir, suite_id="smoke")
            validate_request(request, suite_id="smoke")
            require("expectation" not in request, f"{task_id}: request leaked expectation.", errors)
            require(str((request.get("workspace") or {}).get("fixture") or "").startswith("Eval/Datasets/Behavior/Fixtures/"), f"{task_id}: fixture did not project to canonical Eval dataset.", errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{task_id}: canonical request validation failed: {exc}")
    for focus, minimum in (("routing", 2), ("architecture", 3), ("naming", 3), ("mutation", 1), ("evidence", 1)):
        require(focuses[focus] >= minimum, f"Smoke focus {focus} requires at least {minimum} cases.", errors)

    production = suite_map.get("production_smoke", {}) or {}
    production_cases = production.get("cases", []) or []
    require(len(production_cases) == 4, "Production smoke must contain four canonical cases.", errors)
    expected = {"GOLDEN-ARCH-001", "GOLDEN-NAMING-001", "GOLDEN-MUTATION-001", "GOLDEN-EVIDENCE-001"}
    require(set(production_contracts) == expected, "Production contract set drifted.", errors)
    for item in production_cases:
        task_id = str(item.get("golden_task_id") or "")
        if task_id not in cases or task_id not in production_contracts:
            errors.append(f"Invalid production case: {task_id}")
            continue
        case_dir = ROOT / "Artifacts" / "BehaviorEval" / "phase8-production-protocol" / task_id
        try:
            request = build_request(
                "phase8-production", "revision", cases[task_id], item, case_dir,
                suite_id="production_smoke", production_contract=production_contracts[task_id],
            )
            validate_request(request, suite_id="production_smoke")
            task = request.get("task", {}) or {}
            require("expectation" not in request, f"{task_id}: production request leaked expectation.", errors)
            for key in ("required_signals", "forbidden_signals", "required_policies", "required_gates", "expected_route"):
                require(key not in task, f"{task_id}: production task leaked {key}.", errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{task_id}: production request validation failed: {exc}")

    command = build_executor_command(["python", "adapter.py"], Path("request.yaml"), Path("case-output"))
    require(command[-4:] == ["--request", "request.yaml", "--output", "case-output"], "Runtime executor command formatting drifted.", errors)

    runner_source = CANONICAL_RUNNER.read_text(encoding="utf-8")
    adapter_source = RUNTIME_ADAPTER.read_text(encoding="utf-8")
    for token in ("subprocess", "process_runtime", "Runtime.Runner", "Runtime.Dispatcher"):
        require(token not in runner_source, f"Canonical Behavior evaluator contains execution token: {token}", errors)
        require(token not in adapter_source, f"Runtime->Eval adapter contains execution token: {token}", errors)
    require("changed_paths" in adapter_source, "Runtime adapter must preserve changed_paths.", errors)
    require("diff" not in adapter_source.lower(), "Runtime adapter must not reconstruct canonical facts from diff text.", errors)
    require(not REMOVED_COMPATIBILITY_ROOT.exists(), "Eval/Compatibility must remain absent after Phase 8 cutover.", errors)

    if errors:
        print("Behavior Eval validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Behavior Eval validation passed: Eval grades only; Runtime executes; compatibility execution shim is removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
