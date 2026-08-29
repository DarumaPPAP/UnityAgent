"""Authoritative current state store.

Orchestration may construct state patches, but only Persistence mutates the
durable current records.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from Persistence.Store.atomic_store import PersistenceError, atomic_write_json, read_json, sha256_json, write_immutable_json, relative_ref
from Persistence.Store.layout import PersistenceLayout

EXECUTION_STATUSES = {"idle", "running", "waiting", "blocked", "completed", "failed", "cancelled"}
LOOP_DECISIONS = {"continue", "replan", "exit", "blocked"}


def _require(record: dict[str, Any], fields: set[str], kind: str) -> None:
    missing = sorted(fields - set(record))
    if missing:
        raise PersistenceError("contract_missing_field", f"{kind} missing required fields: {missing}")


class StateStore:
    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

    def save_execution_state(self, record: dict[str, Any]) -> str:
        _require(record, {"schema_version", "run_id", "status", "current_step_id", "current_action_id", "evidence_refs", "updated_at"}, "ExecutionState")
        if record.get("schema_version") != "1.0" or record.get("status") not in EXECUTION_STATUSES:
            raise PersistenceError("invalid_execution_state", "unsupported ExecutionState version or status")
        run_id = str(record["run_id"])
        atomic_write_json(self.layout.execution_state(run_id), deepcopy(record))
        return relative_ref(self.layout.root, self.layout.execution_state(run_id))

    def load_execution_state(self, run_id: str) -> dict[str, Any]:
        record = read_json(self.layout.execution_state(run_id))
        if record.get("run_id") != run_id:
            raise PersistenceError("state_identity_mismatch", "ExecutionState run_id does not match path")
        return record

    def save_workflow_state(self, record: dict[str, Any]) -> str:
        _require(record, {"schema_version", "run_id", "parent_graph_id", "active_subgraph_id", "active_node_id", "shared_state_refs", "gate_state_refs", "updated_at"}, "WorkflowState")
        if record.get("schema_version") != "1.0":
            raise PersistenceError("invalid_workflow_state", "unsupported WorkflowState version")
        run_id = str(record["run_id"])
        atomic_write_json(self.layout.workflow_state(run_id), deepcopy(record))
        return relative_ref(self.layout.root, self.layout.workflow_state(run_id))

    def load_workflow_state(self, run_id: str) -> dict[str, Any]:
        record = read_json(self.layout.workflow_state(run_id))
        if record.get("run_id") != run_id:
            raise PersistenceError("state_identity_mismatch", "WorkflowState run_id does not match path")
        return record

    def save_loop_control_state(self, record: dict[str, Any]) -> str:
        _require(record, {"schema_version", "run_id", "loop_id", "semantic_attempt", "progress_marker", "decision", "updated_at"}, "LoopControlState")
        if record.get("schema_version") != "1.0" or record.get("decision") not in LOOP_DECISIONS:
            raise PersistenceError("invalid_loop_control_state", "unsupported LoopControlState version or decision")
        if int(record.get("semantic_attempt", -1)) < 0:
            raise PersistenceError("invalid_loop_control_state", "semantic_attempt must be non-negative")
        run_id, loop_id = str(record["run_id"]), str(record["loop_id"])
        atomic_write_json(self.layout.loop_state(run_id, loop_id), deepcopy(record))
        return relative_ref(self.layout.root, self.layout.loop_state(run_id, loop_id))

    def load_loop_control_state(self, run_id: str, loop_id: str) -> dict[str, Any]:
        record = read_json(self.layout.loop_state(run_id, loop_id))
        if record.get("run_id") != run_id or record.get("loop_id") != loop_id:
            raise PersistenceError("state_identity_mismatch", "LoopControlState identity does not match path")
        return record

    def snapshot_run(self, run_id: str, loop_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
        """Snapshot current state to content-addressed immutable files."""
        records: dict[str, dict[str, Any]] = {
            "execution_state": self.load_execution_state(run_id),
            "workflow_state": self.load_workflow_state(run_id),
        }
        for loop_id in loop_ids:
            records[f"loop:{loop_id}"] = self.load_loop_control_state(run_id, loop_id)

        refs: dict[str, str] = {}
        hashes: dict[str, str] = {}
        for key, record in records.items():
            digest = sha256_json(record)
            if key.startswith("loop:"):
                identity = key.split(":", 1)[1]
                path = self.layout.snapshot(run_id, "loop-control-state", digest, identity)
            else:
                kind = key.replace("_", "-")
                path = self.layout.snapshot(run_id, kind, digest)
            write_immutable_json(path, record)
            refs[key] = relative_ref(self.layout.root, path)
            hashes[key] = digest
        return refs, hashes
