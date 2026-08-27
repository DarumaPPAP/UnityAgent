#!/usr/bin/env python3
"""Validate UnityAgent Actual Behavior Eval v1 protocol without invoking a model."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from derive_signals import derive_evidence_claims, derive_signals
from normalize_result import (
    BehaviorEvidenceError,
    assert_no_secret_fields,
    normalize_case_result,
    resolve_case_path,
)
from run_behavior_eval import build_executor_command, build_request, validate_request

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / ".ai" / "eval" / "behavior-eval-contract.yaml"
REQUEST_SCHEMA = ROOT / "Tests" / "BehaviorEval" / "behavior-eval-request.schema.yaml"
ENVELOPE_SCHEMA = ROOT / "Tests" / "BehaviorEval" / "execution-envelope.schema.yaml"
SUITES = ROOT / "Tests" / "BehaviorEval" / "suites.yaml"
GOLDEN_CASES = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
CANDIDATE_SCHEMA = ROOT / "Tests" / "GoldenTasks" / "candidate-result.schema.yaml"
PROTOCOL_FIXTURE = ROOT / "Tests" / "BehaviorEval" / "ProtocolFixtures" / "valid"
RUNNER = ROOT / "Tools" / "BehaviorEval" / "run_behavior_eval.py"
GOLDEN_RUNNER = ROOT / "Tools" / "GoldenEval" / "run_golden_evals.py"


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def find_suite_case(suite: dict, task_id: str) -> dict:
    for item in suite.get("cases", []) or []:
        if isinstance(item, dict) and item.get("golden_task_id") == task_id:
            return item
    raise KeyError(task_id)


def main() -> int:
    errors: list[str] = []

    try:
        contract = load_yaml(CONTRACT)
        request_schema = load_yaml(REQUEST_SCHEMA)
        envelope_schema = load_yaml(ENVELOPE_SCHEMA)
        suite_doc = load_yaml(SUITES)
        golden_doc = load_yaml(GOLDEN_CASES)
        candidate_schema = load_yaml(CANDIDATE_SCHEMA)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Behavior Eval validation failed:\n- {exc}")
        return 1

    rules = contract.get("rules", {}) or {}
    for rule in (
        "production_execution_path_required",
        "evaluation_specific_agent_behavior_forbidden",
        "actual_behavior_requires_execution_evidence",
        "agent_self_report_is_supporting_evidence_only",
        "one_agent_attempt_for_smoke",
        "unavailable_is_not_passed",
        "broken_eval_is_not_model_failure",
        "mutation_requires_sandbox",
        "main_workspace_mutation_forbidden",
        "provider_sdk_dependency_in_UnityAgent_forbidden",
    ):
        require(rules.get(rule) is True, f"behavior-eval-contract missing required true rule: {rule}", errors)

    ownership = contract.get("ownership", {}) or {}
    require(
        ownership.get("behavior_and_grading") == "DarumaPPAP/UnityAgent",
        "Behavior/grading ownership must remain DarumaPPAP/UnityAgent.",
        errors,
    )
    require(
        ownership.get("execution_runtime") == "DarumaPPAP/Unity-Graph-Engineering",
        "Execution runtime ownership must remain DarumaPPAP/Unity-Graph-Engineering.",
        errors,
    )

    require(request_schema.get("schema_version") == "1.0", "Behavior request schema must be version 1.0.", errors)
    require(envelope_schema.get("schema_version") == "1.0", "Execution envelope schema must be version 1.0.", errors)
    require(candidate_schema.get("schema_version") == "1.3", "Golden Candidate schema must be version 1.3.", errors)

    golden_cases = {
        str(case.get("id")): case
        for case in golden_doc.get("cases", []) or []
        if isinstance(case, dict) and case.get("id")
    }
    suites = suite_doc.get("suites", {}) or {}
    smoke = suites.get("smoke", {}) or {}
    smoke_cases = smoke.get("cases", []) or []
    require(8 <= len(smoke_cases) <= 12, f"Smoke suite must contain 8-12 cases; found {len(smoke_cases)}.", errors)
    require(int(smoke.get("max_agent_attempts", 0)) == 1, "Smoke suite must use exactly one Agent attempt.", errors)
    require(smoke.get("blocking_candidate") is False, "v1 smoke must remain non-blocking during record-only rollout.", errors)
    require(smoke.get("rollout") == "record_only", "v1 smoke rollout must start as record_only.", errors)

    ids = [str(item.get("golden_task_id") or "") for item in smoke_cases if isinstance(item, dict)]
    duplicates = [task_id for task_id, count in Counter(ids).items() if task_id and count > 1]
    require(not duplicates, f"Smoke suite contains duplicate Golden Task IDs: {duplicates}", errors)

    focus_counts: Counter[str] = Counter()
    for item in smoke_cases:
        if not isinstance(item, dict):
            errors.append("Smoke suite case must be a mapping.")
            continue
        task_id = str(item.get("golden_task_id") or "")
        require(task_id in golden_cases, f"Smoke suite references unknown Golden Task: {task_id}", errors)
        for focus in item.get("focus", []) or []:
            focus_counts[str(focus)] += 1
        require(item.get("mutation_mode") == "sandbox", f"{task_id}: mutation_mode must be sandbox.", errors)
        fixture = ROOT / str(item.get("workspace_fixture") or "")
        require(fixture.exists(), f"{task_id}: workspace fixture does not exist: {fixture}", errors)
        evidence = item.get("evidence", {}) or {}
        required_evidence = set(evidence.get("require", []) or [])
        require(
            {"response", "context_manifest", "artifact_index"}.issubset(required_evidence),
            f"{task_id}: response/context_manifest/artifact_index must be required evidence.",
            errors,
        )
        if "mutation" in (item.get("focus", []) or []):
            require("diff" in required_evidence, f"{task_id}: Mutation case must require diff evidence.", errors)

    require(focus_counts["routing"] >= 2, "Smoke suite requires at least 2 routing-focused cases.", errors)
    require(focus_counts["architecture"] >= 3, "Smoke suite requires at least 3 architecture-focused cases.", errors)
    require(focus_counts["naming"] >= 3, "Smoke suite requires at least 3 naming-focused cases.", errors)
    require(focus_counts["mutation"] >= 1, "Smoke suite requires at least 1 mutation-focused case.", errors)
    require(focus_counts["evidence"] >= 1, "Smoke suite requires at least 1 evidence-focused case.", errors)

    # Build every request and prove Golden expectations are not leaked to the executor.
    for item in smoke_cases:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("golden_task_id") or "")
        golden_case = golden_cases.get(task_id)
        if golden_case is None:
            continue
        case_dir = ROOT / "Artifacts" / "BehaviorEval" / "protocol-validation" / "cases" / task_id
        try:
            request = build_request(
                "protocol-validation",
                "fixture-unityagent-revision",
                golden_case,
                item,
                case_dir,
                suite_id="smoke",
            )
            require("expectation" not in request, f"{task_id}: request leaked Golden expectation.", errors)
            require(request.get("task") == golden_case.get("task"), f"{task_id}: request task differs from Golden task.", errors)
            validate_request(request, suite_id="smoke")
        except Exception as exc:  # noqa: BLE001 - validation reports all protocol issues together.
            errors.append(f"{task_id}: request validation failed: {exc}")

    # Validate the checked-in request fixture with the same runtime validator.
    try:
        validate_request(load_yaml(PROTOCOL_FIXTURE / "request.yaml"), suite_id="smoke")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Protocol request fixture failed validation: {exc}")

    # Evidence -> Candidate Result must be derivable without Agent-authored Candidate YAML.
    try:
        naming_case = golden_cases["GOLDEN-NAMING-003"]
        naming_suite_case = find_suite_case(smoke, "GOLDEN-NAMING-003")
        candidate = normalize_case_result(PROTOCOL_FIXTURE, naming_case, naming_suite_case)
        require(candidate.get("route") == "architecture-design", "Normalizer must derive route from Context Manifest.", errors)
        require(
            "semantic_type_naming" in set(candidate.get("applied_policies", []) or []),
            "Normalizer must derive applied policy from Context Manifest.",
            errors,
        )
        require(candidate.get("attempt_count") == 1, "Normalizer must derive Agent attempt from Execution Envelope.", errors)
        require(
            ((candidate.get("execution", {}) or {}).get("mode")) == "actual_behavior",
            "Normalizer must preserve actual_behavior execution provenance.",
            errors,
        )
        require(
            candidate.get("generated_artifacts"),
            "Normalizer must derive generated artifacts from artifact-index.yaml and real files.",
            errors,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Valid Protocol Fixture normalization failed: {exc}")

    # Missing/unproven runtime evidence must turn a runtime success claim into evidence_overclaim.
    claim_signals, claim_failures, _ = derive_evidence_claims(
        "Unity上で動作確認済みです。",
        {"compile": "unavailable", "playmode": "unavailable"},
    )
    require("runtime_pass_claim" in claim_signals, "Runtime claim must be detected deterministically.", errors)
    require("evidence_overclaim" in claim_failures, "Unproven runtime claim must map to evidence_overclaim.", errors)

    # Mutation diff must prove bounded scope and fail closed on unrelated paths.
    mutation_case = golden_cases.get("GOLDEN-MUTATION-001", {})
    mutation_suite_case = find_suite_case(smoke, "GOLDEN-MUTATION-001")
    bounded_diff = """diff --git a/CameraDebugger.cs b/CameraDebugger.cs\n--- a/CameraDebugger.cs\n+++ b/CameraDebugger.cs\n@@ -1 +1 @@\n-old\n+new\n"""
    bounded = derive_signals(
        mutation_case,
        mutation_suite_case,
        manifest_route="csharp-local-fix",
        response_text="",
        diff_text=bounded_diff,
        artifacts=[],
        gates={"static_review": "passed", "compile": "passed"},
    )
    require("bounded_patch" in set(bounded.get("signals", []) or []), "Allowed-path diff must derive bounded_patch.", errors)
    require("mutation_violation" not in set(bounded.get("failure_types", []) or []), "Allowed-path diff must not fail mutation scope.", errors)

    unrelated_diff = """diff --git a/Other.cs b/Other.cs\n--- a/Other.cs\n+++ b/Other.cs\n@@ -1 +1 @@\n-old\n+new\n"""
    unrelated = derive_signals(
        mutation_case,
        mutation_suite_case,
        manifest_route="csharp-local-fix",
        response_text="",
        diff_text=unrelated_diff,
        artifacts=[],
        gates={"static_review": "passed", "compile": "passed"},
    )
    require(
        "mutation_violation" in set(unrelated.get("failure_types", []) or []),
        "Out-of-scope diff must map to mutation_violation.",
        errors,
    )

    # Protocol must fail closed on secrets and path traversal.
    try:
        assert_no_secret_fields({"executor": {"api_key": "must-not-be-stored"}})
        errors.append("Secret-like envelope fields must be rejected.")
    except BehaviorEvidenceError:
        pass

    try:
        resolve_case_path(PROTOCOL_FIXTURE, "../escape.yaml", required=False)
        errors.append("Evidence path traversal must be rejected.")
    except BehaviorEvidenceError:
        pass

    command = build_executor_command(
        ["python", "adapter.py"],
        Path("request.yaml"),
        Path("case-output"),
    )
    require(isinstance(command, list), "Executor command must remain an argument list.", errors)
    require(command[-4:] == ["--request", "request.yaml", "--output", "case-output"], "Executor protocol arguments are incorrect.", errors)
    require("shell=True" not in RUNNER.read_text(encoding="utf-8"), "Behavior runner must never use shell=True.", errors)
    require(
        "Artifacts/BehaviorEval" in GOLDEN_RUNNER.read_text(encoding="utf-8"),
        "Golden Runner must support Actual Behavior artifact root.",
        errors,
    )

    if errors:
        print("Behavior Eval validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Behavior Eval validation passed: "
        f"{len(smoke_cases)} smoke cases / request+envelope v1 / evidence normalizer / diff+overclaim guards."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
