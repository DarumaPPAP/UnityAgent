#!/usr/bin/env python3
"""Validate typed Context Manifest files or run the v3.1 runtime self-test."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

from context_manifest_runtime import (
    ManifestError,
    apply_gate_evidence,
    build_manifest,
    load_yaml,
    project_execution_graph,
    validate_manifest,
)
from execution_graph_validator import validate_execution_graph


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / ".ai" / "context-manifest.schema.yaml"
REQUEST_A1 = ROOT / "Tests" / "ContextManifest" / "requests" / "csharp-local-fix.yaml"
REQUEST_A2 = ROOT / "Tests" / "ContextManifest" / "requests" / "csharp-local-fix-retry.yaml"
sys.path.insert(0, str(ROOT / "Tools" / "ContextBudget"))

from context_budget_runtime import validate_budget_report  # noqa: E402


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def expect(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def run_self_test() -> list[str]:
    errors: list[str] = []

    try:
        schema = load_yaml(SCHEMA_PATH)
        expect(schema.get("schema_version") == "3.1", "Context Manifest schema must be v3.1.", errors)
        runtime = schema.get("runtime", {})
        for key in (
            "builder",
            "evidence_recorder",
            "validator",
            "graph_projector",
            "budget_engine",
            "budget_validator",
        ):
            expect(bool(runtime.get(key)), f"Context Manifest runtime missing {key}.", errors)

        request_a1 = load_yaml(REQUEST_A1)
        manifest_a1 = build_manifest(ROOT, request_a1)
        errors.extend(validate_manifest(ROOT, manifest_a1))

        expect(manifest_a1["manifest"]["attempt"] == 1, "Initial manifest attempt must be 1.", errors)
        expect(manifest_a1["task"]["route"] == "csharp-local-fix", "Initial manifest route mismatch.", errors)
        expect(
            manifest_a1["context"]["context_pack"]["source_path"]
            == ".ai/context-packs/csharp-local-fix.yaml",
            "Context Pack must be derived from canonical route.",
            errors,
        )
        expect(
            manifest_a1["harness"]["task_contract"]["source_path"]
            == ".ai/harness/task-contracts/csharp-local-fix.yaml",
            "Task Contract must be derived from canonical route.",
            errors,
        )
        expect(
            {gate["id"] for gate in manifest_a1["harness"]["quality_gates"] if gate["requirement"] == "required"}
            == {"static_review", "compile"},
            "Required Quality Gates were not derived from Task Contract.",
            errors,
        )
        expect(
            "unity_version_when_api_sensitive" in manifest_a1["execution"]["unresolved_bindings"],
            "Missing required input must remain an unresolved binding.",
            errors,
        )

        required_repository_paths = {
            item["source_path"]
            for item in manifest_a1["context"]["required_context"]
            if item.get("reference_type") == "repository_reference"
        }
        expect(
            required_repository_paths
            == {
                "SkillReferences/CODING_STANDARDS.md",
                "SkillReferences/CODE_FORMATTING_STANDARDS.md",
            },
            "Typed repository references were not selected from the CSharp Context Pack.",
            errors,
        )
        expect(
            all(
                item.get("reference_type") == "repository_reference"
                for item in manifest_a1["context"]["required_context"]
            ),
            "Required Context must not fall back to scalar/path heuristics.",
            errors,
        )

        project_facts_a1 = manifest_a1["project_facts"]["loaded"]
        expect(len(project_facts_a1) == 1, "Initial fixture must load one Project Fact.", errors)
        if project_facts_a1:
            fact = project_facts_a1[0]
            expect(fact.get("source_kind") == "detected_project", "Project Fact source_kind mismatch.", errors)
            expect(fact.get("revision") == "sha256:golden-project-version-v1", "Project Fact revision mismatch.", errors)
            expect(fact.get("observed_at_attempt") == 1, "Project Fact observation attempt mismatch.", errors)
            expect(
                fact.get("freshness", {}).get("status") == "current"
                and fact.get("freshness", {}).get("checked_at_attempt") == 1,
                "Attempt 1 current Project Fact must be checked in attempt 1.",
                errors,
            )

        conditional_request = copy.deepcopy(request_a1)
        conditional_request["manifest_id"] = "golden-csharp-local-fix-conditional-a1"
        conditional_request["conditions"] = ["architecture_change"]
        conditional_manifest = build_manifest(ROOT, conditional_request)
        conditional_paths = {
            item["source_path"] for item in conditional_manifest["context"]["conditional_context"]
        }
        expect(
            conditional_paths
            == {
                "SkillReferences/ARCHITECTURE_STANDARDS.md",
                "SkillReferences/ARCHITECTURE_DECISION_POLICY.md",
            },
            "Typed conditional repository references were not selected correctly.",
            errors,
        )
        expect(
            all(item.get("condition") == "architecture_change" for item in conditional_manifest["context"]["conditional_context"]),
            "Conditional Context must preserve the activating condition.",
            errors,
        )

        manifest_a1 = apply_gate_evidence(
            ROOT,
            manifest_a1,
            gate="static_review",
            status="passed",
            evidence_id="static-review-a1",
            reason="runtime_evidence",
            source_path="ValidationResults/static-review-a1.txt",
        )
        expect(
            manifest_a1["execution"]["status"] == "in_progress",
            "Passing only one required gate must keep execution in_progress.",
            errors,
        )

        manifest_a1 = apply_gate_evidence(
            ROOT,
            manifest_a1,
            gate="compile",
            status="failed",
            evidence_id="compile-a1",
            reason="runtime_evidence",
            source_path="ValidationResults/compile-a1.txt",
            failure_reason="CS0103_missing_symbol",
        )
        errors.extend(validate_manifest(ROOT, manifest_a1))
        expect(manifest_a1["execution"]["status"] == "failed", "Failed required gate must fail execution.", errors)

        graph_a1 = project_execution_graph(
            ROOT,
            manifest_a1,
            "Artifacts/ContextManifests/golden-csharp-local-fix-a1.yaml",
        )
        errors.extend(validate_execution_graph(ROOT, graph_a1))
        edge_types = {edge["type"] for edge in graph_a1["edges"]}
        for edge_type in (
            "classifies_as",
            "selects",
            "applies_policy",
            "reads_source",
            "allows_mutation",
            "prohibits_mutation",
            "requires_gate",
            "produces_evidence",
            "validates",
        ):
            expect(edge_type in edge_types, f"Execution Graph missing edge type: {edge_type}", errors)

        request_a2 = load_yaml(REQUEST_A2)
        manifest_a2 = build_manifest(ROOT, request_a2, manifest_a1)
        errors.extend(validate_manifest(ROOT, manifest_a2))
        expect(manifest_a2["manifest"]["attempt"] == 2, "Retry attempt must increment to 2.", errors)
        expect(
            manifest_a2["manifest"].get("previous_manifest_id") == manifest_a1["manifest"]["id"],
            "Retry manifest must reference previous manifest id.",
            errors,
        )
        expect(
            manifest_a2["execution"].get("previous_failure", {}).get("status") == "failed",
            "Retry manifest must carry previous failure summary.",
            errors,
        )
        retry_facts = manifest_a2["project_facts"]["loaded"]
        expect(len(retry_facts) == 1, "Retry fixture must explicitly supply its Project Fact.", errors)
        if retry_facts:
            retry_fact = retry_facts[0]
            expect(
                retry_fact.get("observed_at_attempt") == 1
                and retry_fact.get("freshness", {}).get("checked_at_attempt") == 2,
                "Retry may preserve observation history only when freshness is rechecked in attempt 2.",
                errors,
            )

        invalid_retry_freshness = copy.deepcopy(manifest_a2)
        invalid_retry_freshness["project_facts"]["loaded"][0]["freshness"]["checked_at_attempt"] = 1
        invalid_errors = validate_manifest(ROOT, invalid_retry_freshness)
        expect(
            any("Current Project Fact must be checked in manifest attempt 2" in error for error in invalid_errors),
            "Validator must reject a retry that implicitly reuses a previous current Project Fact.",
            errors,
        )

        stale_retry_fact = copy.deepcopy(manifest_a2)
        stale_retry_fact["project_facts"]["loaded"][0]["freshness"] = {
            "status": "stale",
            "checked_at_attempt": 1,
        }
        stale_errors = validate_manifest(ROOT, stale_retry_fact)
        expect(
            not any("Current Project Fact must be checked" in error for error in stale_errors),
            "A stale Project Fact may retain an older check, but must not be represented as current.",
            errors,
        )

        graph_a2 = project_execution_graph(
            ROOT,
            manifest_a2,
            "Artifacts/ContextManifests/golden-csharp-local-fix-a2.yaml",
        )
        errors.extend(validate_execution_graph(ROOT, graph_a2))
        expect(
            any(edge["type"] == "retries_as" for edge in graph_a2["edges"]),
            "Retry Execution Graph must contain retries_as edge.",
            errors,
        )

        conditional_failure = build_manifest(ROOT, request_a1)
        conditional_failure = apply_gate_evidence(
            ROOT,
            conditional_failure,
            gate="static_review",
            status="passed",
            evidence_id="static-review-conditional",
            reason="runtime_evidence",
        )
        conditional_failure = apply_gate_evidence(
            ROOT,
            conditional_failure,
            gate="compile",
            status="passed",
            evidence_id="compile-conditional",
            reason="runtime_evidence",
        )
        expect(
            conditional_failure["execution"]["status"] == "passed",
            "All required gates passed must produce passed before conditional validation runs.",
            errors,
        )
        conditional_failure = apply_gate_evidence(
            ROOT,
            conditional_failure,
            gate="playmode",
            status="failed",
            evidence_id="playmode-conditional",
            reason="runtime_evidence",
            failure_reason="playmode_regression",
        )
        errors.extend(validate_manifest(ROOT, conditional_failure))
        expect(
            conditional_failure["execution"]["status"] == "failed",
            "An activated conditional gate failure must fail execution.",
            errors,
        )

        unavailable = build_manifest(ROOT, request_a1)
        unavailable = apply_gate_evidence(
            ROOT,
            unavailable,
            gate="static_review",
            status="passed",
            evidence_id="static-review-unavailable",
            reason="runtime_evidence",
        )
        unavailable = apply_gate_evidence(
            ROOT,
            unavailable,
            gate="compile",
            status="unavailable",
            evidence_id="compile-unavailable",
            reason="runtime_evidence",
            remaining_validation="Run Unity compile when the execution environment becomes available.",
        )
        errors.extend(validate_manifest(ROOT, unavailable))
        expect(
            unavailable["execution"]["status"] == "complete_with_unavailable",
            "Unavailable required gate must not be reported as passed.",
            errors,
        )

        invalid_unavailable = copy.deepcopy(unavailable)
        invalid_unavailable["execution"]["evidence"][-1].pop("remaining_validation", None)
        invalid_errors = validate_manifest(ROOT, invalid_unavailable)
        expect(
            any("remaining_validation" in error for error in invalid_errors),
            "Validator must reject unavailable evidence without remaining_validation.",
            errors,
        )

        invalid_route = copy.deepcopy(manifest_a2)
        invalid_route["task"]["route"] = "shader-change"
        invalid_errors = validate_manifest(ROOT, invalid_route)
        expect(bool(invalid_errors), "Validator must reject route/manifest binding drift.", errors)

    except ManifestError as exc:
        errors.extend(exc.errors)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"Context Manifest self-test crashed: {exc}")

    return errors


def validate_files(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        try:
            manifest = load_yaml(path)
            file_errors = validate_manifest(ROOT, manifest)
            errors.extend(f"{path}: {error}" for error in file_errors)

            budget = manifest.get("budget")
            if not isinstance(budget, dict):
                errors.append(f"{path}: canonical Context Manifest file requires budget report")
            else:
                budget_errors = validate_budget_report(manifest, budget)
                errors.extend(f"{path}: {error}" for error in budget_errors)
                if budget.get("contract") != ".ai/context-budget.yaml":
                    errors.append(f"{path}: budget.contract must reference .ai/context-budget.yaml")
        except ManifestError as exc:
            errors.extend(f"{path}: {error}" for error in exc.errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="*", help="Manifest YAML paths. Omit to run self-test.")
    args = parser.parse_args()

    if args.manifests:
        errors = validate_files([resolve_path(value) for value in args.manifests])
    else:
        errors = run_self_test()

    if errors:
        print("Context Manifest validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Context Manifest validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
