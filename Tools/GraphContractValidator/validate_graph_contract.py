#!/usr/bin/env python3
"""Validate UnityAgent graph-readiness contracts for Definition and Execution views."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


GRAPH_CONTRACT_PATH = Path(".ai/graph-contract.yaml")
CONTEXT_MANIFEST_PATH = Path(".ai/context-manifest.schema.yaml")

REQUIRED_NODE_TYPES = {
    "task",
    "task_fingerprint",
    "route",
    "policy",
    "project_fact",
    "context_pack",
    "knowledge",
    "source",
    "task_contract",
    "mutation_rule",
    "risk_level",
    "quality_gate",
    "skill",
    "tool",
    "evidence",
    "attempt",
    "golden_task",
}

REQUIRED_EDGE_TYPES = {
    "classifies_as",
    "selects",
    "requires",
    "conditionally_requires",
    "excludes",
    "applies_policy",
    "uses_skill",
    "uses_knowledge",
    "reads_source",
    "allows_mutation",
    "prohibits_mutation",
    "requires_gate",
    "uses_tool",
    "produces_evidence",
    "validates",
    "depends_on",
    "escalates_to",
    "retries_as",
    "evaluated_by",
}

REQUIRED_PROVENANCE_REASONS = {
    "canonical_binding",
    "mutation_target",
    "direct_dependency",
    "required_context",
    "conditional_context",
    "excluded_context",
    "user_policy",
    "project_fact",
    "harness_contract",
    "quality_gate",
    "runtime_evidence",
    "regression_expectation",
}

REQUIRED_VIEWS = {"architecture", "task", "execution"}


def load_yaml(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ValueError(f"Expected mapping document: {path}")
    return document


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    graph_path = root / GRAPH_CONTRACT_PATH
    manifest_path = root / CONTEXT_MANIFEST_PATH

    if not graph_path.is_file():
        return [f"Missing file: {GRAPH_CONTRACT_PATH}"]
    if not manifest_path.is_file():
        return [f"Missing file: {CONTEXT_MANIFEST_PATH}"]

    try:
        graph = load_yaml(graph_path)
        manifest = load_yaml(manifest_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [str(exc)]

    source_of_truth = graph.get("source_of_truth", {})
    if source_of_truth.get("canonical_yaml_remains_authoritative") is not True:
        errors.append("Canonical YAML must remain authoritative for graph projection.")
    if source_of_truth.get("graph_is_derived_view") is not True:
        errors.append("Graph must remain a derived view.")
    if source_of_truth.get("graph_editor_mutation_enabled") is not False:
        errors.append("Graph editor mutation must remain disabled until explicitly redesigned.")

    graph_kinds = graph.get("graph_kinds", {})
    for graph_kind in ("definition", "execution"):
        if graph_kind not in graph_kinds:
            errors.append(f"Missing graph kind: {graph_kind}")

    node_contract = graph.get("node_contract", {})
    if node_contract.get("stable_node_ids_required") is not True:
        errors.append("Stable node IDs must be required.")
    if node_contract.get("node_type_required") is not True:
        errors.append("Node type must be required.")
    if node_contract.get("source_provenance_required") is not True:
        errors.append("Source provenance must be required.")

    node_types = set(graph.get("node_types", []))
    for node_type in sorted(REQUIRED_NODE_TYPES - node_types):
        errors.append(f"Missing required node type: {node_type}")

    edge_contract = graph.get("edge_contract", {})
    if edge_contract.get("typed_edges_required") is not True:
        errors.append("Typed edges must be required.")

    edge_types = set(graph.get("edge_types", []))
    for edge_type in sorted(REQUIRED_EDGE_TYPES - edge_types):
        errors.append(f"Missing required edge type: {edge_type}")

    provenance = graph.get("provenance", {})
    required_provenance = set(provenance.get("required_fields", []))
    for field in ("source_path", "reason"):
        if field not in required_provenance:
            errors.append(f"Missing provenance field: {field}")
    reasons = set(provenance.get("reasons", []))
    for reason in sorted(REQUIRED_PROVENANCE_REASONS - reasons):
        errors.append(f"Missing provenance reason: {reason}")

    views = set(graph.get("visualization_contract", {}).get("required_views", []))
    for view in sorted(REQUIRED_VIEWS - views):
        errors.append(f"Missing required visualization view: {view}")

    execution_projection = graph.get("projection_rules", {}).get("execution_graph", {})
    if execution_projection.get("manifest_is_graph_instance") is not True:
        errors.append("Context Manifest must be defined as one Execution Graph instance.")
    if execution_projection.get("runtime_builder") != "Tools/ContextManifest/build_context_manifest.py":
        errors.append("Execution Graph must reference the Context Manifest runtime builder.")
    if execution_projection.get("runtime_projector") != "Tools/ContextManifest/project_execution_graph.py":
        errors.append("Execution Graph must reference the runtime graph projector.")
    if execution_projection.get("generated_artifact_is_not_source_of_truth") is not True:
        errors.append("Generated Execution Graph must remain non-canonical.")

    runtime = manifest.get("runtime", {})
    for key, expected in (
        ("builder", "Tools/ContextManifest/build_context_manifest.py"),
        ("evidence_recorder", "Tools/ContextManifest/record_manifest_evidence.py"),
        ("validator", "Tools/ContextManifest/validate_context_manifest.py"),
        ("graph_projector", "Tools/ContextManifest/project_execution_graph.py"),
    ):
        if runtime.get(key) != expected:
            errors.append(f"Context Manifest runtime {key} must be {expected}.")
    if runtime.get("generated_manifest_is_not_canonical_policy") is not True:
        errors.append("Generated Context Manifest must remain non-canonical Policy.")

    manifest_projection = manifest.get("graph_projection", {})
    if manifest_projection.get("contract") != ".ai/graph-contract.yaml":
        errors.append("Context Manifest must reference .ai/graph-contract.yaml.")
    if manifest_projection.get("graph_kind") != "execution":
        errors.append("Context Manifest graph_kind must be execution.")
    if manifest_projection.get("manifest_is_graph_instance") is not True:
        errors.append("Context Manifest must declare manifest_is_graph_instance: true.")
    if manifest_projection.get("typed_edges_required") is not True:
        errors.append("Context Manifest must preserve typed edges.")
    if manifest_projection.get("provenance_required") is not True:
        errors.append("Context Manifest must preserve provenance.")
    if manifest_projection.get("source_of_truth_remains_canonical_yaml") is not True:
        errors.append("Execution Graph must not replace canonical YAML as source of truth.")

    manifest_root = manifest.get("manifest", {})
    if manifest_root.get("graph_kind") != "execution":
        errors.append("Context Manifest root must declare graph_kind: execution.")
    attempt_contract = manifest_root.get("attempt", {})
    if not isinstance(attempt_contract, dict) or attempt_contract.get("required") is not True:
        errors.append("Context Manifest must require attempt for execution tracing.")
    if attempt_contract.get("minimum") != 1:
        errors.append("Context Manifest attempt minimum must be 1.")

    retry_rules = manifest.get("retry_rules", {})
    if retry_rules.get("retry_decision_owner") != "DarumaPPAP/Unity-Graph-Engineering":
        errors.append("Retry decision ownership must remain in Unity-Graph-Engineering.")
    if retry_rules.get("previous_failure_is_summary_not_context_copy") is not True:
        errors.append("Retry must carry a failure summary instead of copying full previous Context.")

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate(root)

    if errors:
        print("Graph Contract validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Graph Contract validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
