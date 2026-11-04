"""Authoritative current state store.

Orchestration may construct state patches, but only Persistence mutates the
durable current records.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from unityagent.persistence.store.atomic_store import PersistenceError, atomic_write_json, read_json, sha256_json, write_immutable_json, relative_ref, safe_id
from unityagent.persistence.store.layout import PersistenceLayout
from unityagent.resources import resource_root

def _require(record: dict[str, Any], fields: set[str], kind: str) -> None:
    missing = sorted(fields - set(record))
    if missing:
        raise PersistenceError("contract_missing_field", f"{kind} missing required fields: {missing}")


class StateStore:
    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

    def validate_state(self, record: dict[str, Any], kind: str) -> None:
        """保存と復元前検証を同じ正本Schemaへ揃え、検証中は永続状態を変更しない。"""
        if kind not in {"execution-state", "workflow-state", "loop-control-state"}:
            raise ValueError("unsupported State kind")
        code = "invalid_" + kind.replace("-", "_")
        if not isinstance(record, dict):
            raise PersistenceError(code, "State must be an object")
        schema = yaml.safe_load((resource_root() / "src/unityagent/persistence/contracts" / f"{kind}.schema.yaml").read_text(encoding="utf-8"))
        _require(record, set(schema["required"]), schema["title"])
        try:
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
        except ValidationError as exc:
            raise PersistenceError(code, f"{schema['title']} violates its State contract: {exc.message}") from exc
        safe_id(record["run_id"], "run_id")
        if kind == "loop-control-state":
            safe_id(record["loop_id"], "loop_id")

    def save_execution_state(self, record: dict[str, Any]) -> str:
        self.validate_state(record, "execution-state")
        run_id = str(record["run_id"])
        atomic_write_json(self.layout.execution_state(run_id), deepcopy(record))
        return relative_ref(self.layout.root, self.layout.execution_state(run_id))

    def load_execution_state(self, run_id: str) -> dict[str, Any]:
        record = read_json(self.layout.execution_state(run_id))
        self.validate_state(record, "execution-state")
        if record.get("run_id") != run_id:
            raise PersistenceError("state_identity_mismatch", "ExecutionState run_id does not match path")
        return record

    def save_workflow_state(self, record: dict[str, Any]) -> str:
        self.validate_state(record, "workflow-state")
        run_id = str(record["run_id"])
        atomic_write_json(self.layout.workflow_state(run_id), deepcopy(record))
        return relative_ref(self.layout.root, self.layout.workflow_state(run_id))

    def load_workflow_state(self, run_id: str) -> dict[str, Any]:
        record = read_json(self.layout.workflow_state(run_id))
        self.validate_state(record, "workflow-state")
        if record.get("run_id") != run_id:
            raise PersistenceError("state_identity_mismatch", "WorkflowState run_id does not match path")
        return record

    def save_loop_control_state(self, record: dict[str, Any]) -> str:
        self.validate_state(record, "loop-control-state")
        run_id, loop_id = str(record["run_id"]), str(record["loop_id"])
        atomic_write_json(self.layout.loop_state(run_id, loop_id), deepcopy(record))
        return relative_ref(self.layout.root, self.layout.loop_state(run_id, loop_id))

    def load_loop_control_state(self, run_id: str, loop_id: str) -> dict[str, Any]:
        record = read_json(self.layout.loop_state(run_id, loop_id))
        self.validate_state(record, "loop-control-state")
        if record.get("run_id") != run_id or record.get("loop_id") != loop_id:
            raise PersistenceError("state_identity_mismatch", "LoopControlState identity does not match path")
        return record

    def save_task_state(self, record: dict[str, Any]) -> str:
        _require(record, {"schema_version", "run_id", "contract_digest", "definition_fingerprint", "tasks", "project_revisions"}, "TaskState")
        path = self.layout.run_root(record["run_id"]) / "current/task-state.json"
        atomic_write_json(path, deepcopy(record))
        return relative_ref(self.layout.root, path)

    def load_task_state(self, run_id: str) -> dict[str, Any]:
        record = read_json(self.layout.run_root(run_id) / "current/task-state.json")
        if record.get("run_id") != run_id:
            raise PersistenceError("state_identity_mismatch", "TaskState run_id differs")
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
