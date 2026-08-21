"""Build and validate the versioned Loop handoff without owning Loop runtime."""

from __future__ import annotations

from typing import Any


FORBIDDEN_KEYS = {
    "transcript",
    "transcript_body",
    "evidence_body",
    "retry_count",
    "budget",
    "policy_body",
}


def _forbidden_key_present(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in FORBIDDEN_KEYS:
                return key
            found = _forbidden_key_present(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _forbidden_key_present(item)
            if found:
                return found
    return None


def build_to_loop(task: dict[str, Any], manifest: dict[str, Any], harness: dict[str, Any]) -> dict[str, Any]:
    task_data = manifest.get("task", {})
    return {
        "schema_version": "1.0",
        "task_id": task.get("task_id", task_data.get("id")),
        "context_manifest_id": manifest.get("manifest", {}).get("id", manifest.get("id")),
        "route_id": task.get("route_id", task_data.get("route")),
        "task_fingerprint": task.get("task_fingerprint", task_data.get("fingerprint", {})),
        "execution_profile": harness.get("execution_profile"),
        "risk_level": harness.get("risk_level"),
        "selected_contexts": [
            {"id": item.get("id"), "source_hash": item.get("source_hash")}
            for item in task.get("selected_contexts", [])
        ],
        "allowed_mutations": harness.get("allowed_mutations", []),
        "prohibited_mutations": harness.get("prohibited_mutations", []),
        "required_quality_gates": [item.get("id") for item in harness.get("quality_gates", {}).get("required", [])],
        "conditional_quality_gates": [item.get("id") for item in harness.get("quality_gates", {}).get("conditional", [])],
        "unresolved_bindings": harness.get("unresolved_bindings", []),
    }


def build_from_loop(result: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "run_id", "node_id", "attempt", "verdict", "evidence_refs",
        "gate_results", "failure_signature", "stop_reason", "metrics_ref", "next_transition",
    )
    return {"schema_version": "1.0", **{field: result.get(field) for field in fields}}


def validate_handoff(document: dict[str, Any], direction: str) -> list[str]:
    if direction == "to_loop":
        required = [
            "task_id", "context_manifest_id", "route_id", "task_fingerprint",
            "execution_profile", "risk_level", "selected_contexts", "allowed_mutations",
            "prohibited_mutations", "required_quality_gates", "conditional_quality_gates",
            "unresolved_bindings",
        ]
    else:
        required = [
            "run_id", "node_id", "attempt", "verdict", "evidence_refs", "gate_results",
            "failure_signature", "stop_reason", "metrics_ref", "next_transition",
        ]
    errors = [f"missing required field: {field}" for field in required if field not in document]
    forbidden = _forbidden_key_present(document)
    if forbidden:
        errors.append(f"forbidden handoff content: {forbidden}")
    if direction == "to_loop" and document.get("risk_level") == "R0" and document.get("allowed_mutations"):
        errors.append("R0 handoff cannot contain allowed mutations")
    return errors
