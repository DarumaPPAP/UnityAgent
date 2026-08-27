"""Build and validate the versioned Loop handoff without owning Loop runtime."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "2.0"
FORBIDDEN_KEYS = {
    "transcript",
    "transcript_body",
    "evidence_body",
    "retry_count",
    "budget",
    "policy_body",
}
CONTEXT_BUDGET_STATUSES = {
    "within_budget",
    "compression_required",
    "blocked",
    "unmeasured",
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


def _context_budget_decision(manifest: dict[str, Any]) -> dict[str, Any]:
    context_budget = manifest.get("budget", {}) or {}
    return {
        "contract": context_budget.get("contract", ".ai/context-budget.yaml"),
        "profile": context_budget.get("profile"),
        "decision": context_budget.get("decision"),
        "blocking_reasons": list(context_budget.get("blocking_reasons", []) or []),
    }


def build_to_loop(task: dict[str, Any], manifest: dict[str, Any], harness: dict[str, Any]) -> dict[str, Any]:
    task_data = manifest.get("task", {}) or {}
    harness_data = manifest.get("harness", {}) or {}
    task_contract = harness_data.get("task_contract", {}) or {}
    context_budget = _context_budget_decision(manifest)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task.get("task_id", task_data.get("id")),
        "context_manifest_id": manifest.get("manifest", {}).get("id", manifest.get("id")),
        "context_manifest_schema_version": manifest.get("schema_version"),
        "route_id": task.get("route_id", task_data.get("route")),
        "task_fingerprint": task.get("task_fingerprint", task_data.get("fingerprint", {})),
        "task_contract_ref": task.get("task_contract_ref", task_contract.get("source_path")),
        "execution_profile": harness.get("execution_profile"),
        "risk_level": harness.get("risk_level"),
        "selected_contexts": [
            {"id": item.get("id"), "source_hash": item.get("source_hash")}
            for item in task.get("selected_contexts", [])
        ],
        "context_budget_decision": context_budget,
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
    return {"schema_version": SCHEMA_VERSION, **{field: result.get(field) for field in fields}}


def validate_handoff(document: dict[str, Any], direction: str) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"handoff schema_version must be {SCHEMA_VERSION}")

    if direction == "to_loop":
        required = [
            "task_id", "context_manifest_id", "context_manifest_schema_version", "route_id",
            "task_fingerprint", "task_contract_ref", "execution_profile", "risk_level",
            "selected_contexts", "context_budget_decision", "allowed_mutations",
            "prohibited_mutations", "required_quality_gates", "conditional_quality_gates",
            "unresolved_bindings",
        ]
    else:
        required = [
            "run_id", "node_id", "attempt", "verdict", "evidence_refs", "gate_results",
            "failure_signature", "stop_reason", "metrics_ref", "next_transition",
        ]
    errors.extend(f"missing required field: {field}" for field in required if field not in document)

    forbidden = _forbidden_key_present(document)
    if forbidden:
        errors.append(f"forbidden handoff content: {forbidden}")

    if direction == "to_loop":
        if document.get("risk_level") == "R0" and document.get("allowed_mutations"):
            errors.append("R0 handoff cannot contain allowed mutations")

        context_budget = document.get("context_budget_decision")
        if isinstance(context_budget, dict):
            decision = context_budget.get("decision")
            if decision not in CONTEXT_BUDGET_STATUSES:
                errors.append("context_budget_decision.decision must be a canonical Context Budget status")
            if document.get("allowed_mutations") and decision != "within_budget":
                errors.append("mutation handoff requires context budget decision within_budget")
        elif "context_budget_decision" in document:
            errors.append("context_budget_decision must be a mapping")

    return errors
