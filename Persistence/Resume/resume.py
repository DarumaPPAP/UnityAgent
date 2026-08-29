"""Fail-closed resume compatibility evaluation."""
from __future__ import annotations
from copy import deepcopy
from typing import Any

from Persistence.Checkpoint.checkpoint_store import CheckpointStore
from Persistence.Store.atomic_store import PersistenceError, read_json, resolve_ref

CRITICAL_FIELDS = {
    "architecture_version",
    "policy_revision",
    "prompt_revision",
    "context_revision",
    "graph_revision",
    "runtime_profile_revision",
    "tool_schema_revision",
    "checkpoint_schema_revision",
    "evidence_schema_revision",
    "eval_contract_revision",
}


def _diff(saved: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return sorted(key for key in CRITICAL_FIELDS if saved.get(key) != current.get(key))


def evaluate_resume(
    *,
    store_root,
    run_id: str,
    checkpoint_id: str,
    current_definition_fingerprint: dict[str, Any],
    compatibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checkpoints = CheckpointStore(store_root)
    checkpoint = checkpoints.load(run_id, checkpoint_id, verify=True)
    saved = checkpoint["definition_fingerprint"]
    changed = _diff(saved, current_definition_fingerprint)
    compatibility = compatibility or {}

    if not changed:
        return {"decision": "resume", "allowed": True, "changed_fields": [], "required_actions": [], "checkpoint": checkpoint}

    execution = read_json(resolve_ref(checkpoints.layout.root, checkpoint["execution_state_ref"]))
    workflow = read_json(resolve_ref(checkpoints.layout.root, checkpoint["workflow_state_ref"]))
    actions: list[str] = []
    blockers: list[str] = []

    if "architecture_version" in changed:
        blockers.append("architecture_change_requires_human_review")

    if "policy_revision" in changed:
        allowed_pairs = set(tuple(item) for item in compatibility.get("policy_compatible_pairs", []))
        if (saved.get("policy_revision"), current_definition_fingerprint.get("policy_revision")) not in allowed_pairs:
            blockers.append("policy_revision_changed_without_compatibility")
        else:
            actions.append("revalidate_policy_and_approval")

    if {"prompt_revision", "context_revision"} & set(changed):
        if execution.get("current_action_id") is None and execution.get("active_tool_invocation_ref") is None:
            actions.append("rematerialize_context")
        else:
            blockers.append("issued_action_must_not_be_reused")
            actions.append("return_to_safe_orchestration_boundary_and_replan")

    if "graph_revision" in changed:
        graph_maps = compatibility.get("graph_node_maps", {})
        key = f"{saved.get('graph_revision')}->{current_definition_fingerprint.get('graph_revision')}"
        mapping = graph_maps.get(key)
        active_node = workflow.get("active_node_id")
        if active_node is None:
            actions.append("revalidate_graph_entry")
        elif not isinstance(mapping, dict) or active_node not in mapping:
            blockers.append("active_graph_node_has_no_exact_migration")
        else:
            actions.append(f"map_active_node:{active_node}->{mapping[active_node]}")

    if {"runtime_profile_revision", "tool_schema_revision"} & set(changed):
        if execution.get("active_tool_invocation_ref") is not None:
            blockers.append("external_action_may_be_in_flight")
            actions.append("reconcile_external_side_effects")
        else:
            actions.append("revalidate_runtime_action_before_execute")

    if "checkpoint_schema_revision" in changed:
        pairs = set(tuple(item) for item in compatibility.get("checkpoint_compatible_pairs", []))
        pair = (saved.get("checkpoint_schema_revision"), current_definition_fingerprint.get("checkpoint_schema_revision"))
        if pair not in pairs:
            blockers.append("checkpoint_schema_change_requires_tested_migration")
        else:
            actions.append("migrate_checkpoint_copy")

    if "evidence_schema_revision" in changed:
        actions.append("use_versioned_evidence_reader_preserve_original")

    if "eval_contract_revision" in changed:
        actions.append("record_eval_revision_change_for_replay")

    if blockers:
        return {
            "decision": "blocked",
            "allowed": False,
            "changed_fields": changed,
            "required_actions": list(dict.fromkeys(actions)),
            "blockers": blockers,
            "checkpoint": checkpoint,
        }

    return {
        "decision": "resume_with_revalidation" if actions else "resume",
        "allowed": True,
        "changed_fields": changed,
        "required_actions": list(dict.fromkeys(actions)),
        "checkpoint": checkpoint,
    }
