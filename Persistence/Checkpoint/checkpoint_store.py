"""Immutable checkpoint creation, integrity verification, and state-only restoration."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from Persistence.Contracts.definition_fingerprint import validate_definition_fingerprint
from Persistence.State.state_store import StateStore
from Persistence.Evidence.evidence_store import EvidenceStore
from Persistence.Store.atomic_store import (
    PersistenceError, append_jsonl, read_json, resolve_ref,
    sha256_json, write_immutable_json,
)
from Persistence.Store.layout import PersistenceLayout


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checkpoint_hash(record: dict[str, Any]) -> str:
    payload = {k: v for k, v in record.items() if k != "checkpoint_hash"}
    return sha256_json(payload)


class CheckpointStore:
    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)
        self.states = StateStore(root)

    def create(
        self,
        *,
        checkpoint_id: str,
        run_id: str,
        reason: str,
        loop_ids: list[str],
        evidence_refs: list[str],
        definition_fingerprint: dict[str, Any],
        created_at: str | None = None,
    ) -> dict[str, Any]:
        validate_definition_fingerprint(definition_fingerprint)
        loop_ids = list(dict.fromkeys(str(loop_id) for loop_id in loop_ids))
        evidence_refs = list(dict.fromkeys(str(ref) for ref in evidence_refs))

        # A checkpoint may reference only already-durable Evidence. Runtime capture
        # alone is not sufficient to make an Evidence reference historical truth.
        evidence_store = EvidenceStore(self.layout.root)
        for evidence_id in evidence_refs:
            evidence_store.get(evidence_id)

        refs, hashes = self.states.snapshot_run(run_id, loop_ids)
        record = {
            "schema_version": "1.1",
            "checkpoint_id": checkpoint_id,
            "run_id": run_id,
            "created_at": created_at or _now(),
            "reason": reason,
            "execution_state_ref": refs["execution_state"],
            "workflow_state_ref": refs["workflow_state"],
            "loop_control_state_refs": [refs[f"loop:{loop_id}"] for loop_id in loop_ids],
            "evidence_refs": evidence_refs,
            "definition_fingerprint": deepcopy(definition_fingerprint),
            "state_snapshot_hashes": {
                "execution_state": hashes["execution_state"],
                "workflow_state": hashes["workflow_state"],
                "loop_control_states": {
                    loop_id: hashes[f"loop:{loop_id}"] for loop_id in loop_ids
                },
            },
            "migration_from": None,
        }
        record["checkpoint_hash"] = _checkpoint_hash(record)
        path = self.layout.checkpoint(run_id, checkpoint_id)
        created = write_immutable_json(path, record)
        if created:
            append_jsonl(self.layout.checkpoint_events(), {
                "event": "checkpoint_created",
                "checkpoint_id": checkpoint_id,
                "run_id": run_id,
                "checkpoint_hash": record["checkpoint_hash"],
            })
        return record

    def load(self, run_id: str, checkpoint_id: str, *, verify: bool = True) -> dict[str, Any]:
        record = read_json(self.layout.checkpoint(run_id, checkpoint_id))
        if record.get("run_id") != run_id or record.get("checkpoint_id") != checkpoint_id:
            raise PersistenceError("checkpoint_identity_mismatch", "checkpoint identity does not match path")
        if verify:
            self.verify(record)
        return record

    def verify(self, record: dict[str, Any]) -> None:
        validate_definition_fingerprint(record.get("definition_fingerprint"))
        evidence_store = EvidenceStore(self.layout.root)
        for evidence_id in record.get("evidence_refs", []):
            evidence_store.get(str(evidence_id))

        if record.get("schema_version") == "1.1":
            supplied = record.get("checkpoint_hash")
            if not supplied or supplied != _checkpoint_hash(record):
                raise PersistenceError("checkpoint_integrity_failed", "checkpoint hash mismatch")
            hashes = record.get("state_snapshot_hashes") or {}
            checks = [
                ("execution_state", record["execution_state_ref"], hashes.get("execution_state")),
                ("workflow_state", record["workflow_state_ref"], hashes.get("workflow_state")),
            ]
            loop_hashes = hashes.get("loop_control_states") or {}
            for ref in record.get("loop_control_state_refs", []):
                snap = read_json(resolve_ref(self.layout.root, ref))
                loop_id = str(snap.get("loop_id"))
                checks.append((f"loop:{loop_id}", ref, loop_hashes.get(loop_id)))
            for name, ref, expected in checks:
                if not expected:
                    raise PersistenceError("checkpoint_integrity_failed", f"missing snapshot hash for {name}")
                actual = sha256_json(read_json(resolve_ref(self.layout.root, ref)))
                if actual != expected:
                    raise PersistenceError("checkpoint_integrity_failed", f"snapshot hash mismatch for {name}")
        elif record.get("schema_version") == "1.0":
            # Historical canonical v1.0 had no checkpoint hash. Read-only
            # compatibility verifies referenced records exist but never rewrites it.
            for ref in [record["execution_state_ref"], record["workflow_state_ref"], *record.get("loop_control_state_refs", [])]:
                read_json(resolve_ref(self.layout.root, ref))
        else:
            raise PersistenceError("unsupported_checkpoint_schema", f"unsupported checkpoint schema: {record.get('schema_version')}")

    def restore(self, run_id: str, checkpoint_id: str) -> None:
        """Restore only checkpointed current State; Memory and Evidence are never rolled back.

        Callers must perform Resume compatibility evaluation before invoking this
        low-level state restore when definition revisions may have changed.
        """
        record = self.load(run_id, checkpoint_id, verify=True)
        execution = read_json(resolve_ref(self.layout.root, record["execution_state_ref"]))
        workflow = read_json(resolve_ref(self.layout.root, record["workflow_state_ref"]))
        loop_records = [
            read_json(resolve_ref(self.layout.root, ref))
            for ref in record.get("loop_control_state_refs", [])
        ]

        # Exact restore matters: LoopState created after the checkpoint must not
        # survive and silently influence a resumed graph.
        loops_dir = self.layout.run_root(run_id) / "current" / "loops"
        restored_loop_ids = {str(item["loop_id"]) for item in loop_records}
        if loops_dir.is_dir():
            for path in loops_dir.glob("*.json"):
                if path.stem not in restored_loop_ids:
                    path.unlink()

        self.states.save_execution_state(execution)
        self.states.save_workflow_state(workflow)
        for loop_record in loop_records:
            self.states.save_loop_control_state(loop_record)
