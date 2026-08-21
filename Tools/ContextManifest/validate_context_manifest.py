#!/usr/bin/env python3
"""Validate Context Manifest files or run the Phase 6 runtime self-test."""

from __future__ import annotations

import argparse
import copy
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
        expect(schema.get("schema_version") == "3.0", "Context Manifest schema must be v3.0.", errors)
        runtime = schema.get("runtime", {})
        for key in ("builder", "evidence_recorder", "validator", "graph_projector"):
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
