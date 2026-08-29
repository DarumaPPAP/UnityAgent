"""Map Orchestration projections to Persistence contracts without persisting them."""
from __future__ import annotations
from datetime import datetime, timezone


def _now(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat()


def workflow_state_patch(*, run_id: str, parent_graph_id: str, active_subgraph_id: str | None, active_node_id: str | None, shared_state_refs: list[str] | None = None, gate_state_refs: list[str] | None = None, updated_at: str | None = None) -> dict:
    return {"schema_version": "1.0", "run_id": run_id, "parent_graph_id": parent_graph_id, "active_subgraph_id": active_subgraph_id, "active_node_id": active_node_id, "shared_state_refs": list(dict.fromkeys(shared_state_refs or [])), "gate_state_refs": list(dict.fromkeys(gate_state_refs or [])), "updated_at": _now(updated_at)}


def loop_control_state_patch(*, run_id: str, loop_id: str, semantic_attempt: int, progress_marker: str | None, decision: str, replan_reason: str | None = None, updated_at: str | None = None) -> dict:
    if decision not in {"continue", "replan", "exit", "blocked"}:
        raise ValueError("invalid semantic loop decision")
    return {"schema_version": "1.0", "run_id": run_id, "loop_id": loop_id, "semantic_attempt": semantic_attempt, "progress_marker": progress_marker, "decision": decision, "replan_reason": replan_reason, "updated_at": _now(updated_at)}
