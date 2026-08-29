"""Read-only normalization of legacy Graph run-state into canonical state records."""
from __future__ import annotations
from typing import Any

from Persistence.Store.atomic_store import PersistenceError

STATUS_MAP = {
    "planned": "idle",
    "running": "running",
    "blocked": "blocked",
    "approved": "completed",
    "rejected": "failed",
    "escalated": "blocked",
    "cancelled": "cancelled",
}


def normalize_legacy_run_state(
    legacy: dict[str, Any],
    *,
    parent_graph_id: str,
    subgraph_by_node: dict[str, str],
) -> dict[str, Any]:
    run_id = str(legacy.get("run_id") or "").strip()
    if not run_id:
        raise PersistenceError("legacy_state_invalid", "legacy run state has no run_id")
    running_nodes = [node for node in legacy.get("nodes", []) if node.get("status") == "running"]
    if len(running_nodes) > 1:
        raise PersistenceError("legacy_state_ambiguous", "multiple legacy running nodes cannot map to one active node")
    active_node_id = str(running_nodes[0].get("id")) if running_nodes else None
    if active_node_id is not None and active_node_id not in subgraph_by_node:
        raise PersistenceError("legacy_graph_mapping_missing", f"no exact SubGraph mapping for {active_node_id}")
    active_subgraph_id = subgraph_by_node.get(active_node_id) if active_node_id else None
    evidence_refs = sorted({str(ref) for node in legacy.get("nodes", []) for ref in node.get("last_evidence", []) if str(ref)})
    updated_at = str(legacy.get("updated_at") or legacy.get("started_at") or "1970-01-01T00:00:00Z")
    execution = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": STATUS_MAP.get(str(legacy.get("status")), "blocked"),
        "current_step_id": active_node_id,
        # last_action is historical; it is not proof that an external action is still issued/in flight.
        "current_action_id": None,
        "active_tool_invocation_ref": None,
        "evidence_refs": evidence_refs,
        "updated_at": updated_at,
    }
    workflow = {
        "schema_version": "1.0",
        "run_id": run_id,
        "parent_graph_id": parent_graph_id,
        "active_subgraph_id": active_subgraph_id,
        "active_node_id": active_node_id,
        "shared_state_refs": [],
        "gate_state_refs": [],
        "updated_at": updated_at,
    }
    return {
        "execution_state": execution,
        "workflow_state": workflow,
        "loop_control_states": [],
        "diagnostics": [
            "legacy node attempts are not inferred as semantic LoopControlState",
            "legacy last_action is historical and is not reused as a current action",
        ],
    }


def reject_continuation_decision_as_durable_state(value: dict[str, Any]) -> None:
    if value.get("controller") == "native_continuation":
        raise PersistenceError(
            "legacy_projection_not_durable_state",
            "native continuation output is a decision projection, not authoritative LoopControlState",
        )
