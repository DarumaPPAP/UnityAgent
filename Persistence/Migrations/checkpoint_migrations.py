"""Checkpoint migrations always create a new record and preserve the source."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from Persistence.Checkpoint.checkpoint_store import CheckpointStore, _checkpoint_hash
from Persistence.Store.atomic_store import PersistenceError, append_jsonl, read_json, resolve_ref, sha256_json, write_immutable_json


def migrate_v1_0_to_v1_1(
    *,
    store_root,
    run_id: str,
    source_checkpoint_id: str,
    new_checkpoint_id: str,
    current_definition_fingerprint: dict[str, Any],
) -> dict[str, Any]:
    store = CheckpointStore(store_root)
    source = store.load(run_id, source_checkpoint_id, verify=True)
    if source.get("schema_version") != "1.0":
        raise PersistenceError("migration_source_version_mismatch", "source checkpoint must be schema 1.0")

    state_refs = [
        source["execution_state_ref"],
        source["workflow_state_ref"],
        *source.get("loop_control_state_refs", []),
    ]
    if any("/current/" in f"/{str(ref).replace('\\\\', '/')}" for ref in state_refs):
        raise PersistenceError(
            "legacy_checkpoint_mutable_ref_unsafe",
            "legacy checkpoint references mutable current state and cannot be migrated as historical truth",
        )

    execution = read_json(resolve_ref(store.layout.root, source["execution_state_ref"]))
    workflow = read_json(resolve_ref(store.layout.root, source["workflow_state_ref"]))
    loop_hashes: dict[str, str] = {}
    for ref in source.get("loop_control_state_refs", []):
        value = read_json(resolve_ref(store.layout.root, ref))
        loop_hashes[str(value["loop_id"])] = sha256_json(value)

    migrated = deepcopy(source)
    migrated["schema_version"] = "1.1"
    migrated["checkpoint_id"] = new_checkpoint_id
    migrated["definition_fingerprint"] = deepcopy(current_definition_fingerprint)
    migrated["state_snapshot_hashes"] = {
        "execution_state": sha256_json(execution),
        "workflow_state": sha256_json(workflow),
        "loop_control_states": loop_hashes,
    }
    migrated["migration_from"] = {
        "checkpoint_id": source_checkpoint_id,
        "schema_version": "1.0",
    }
    migrated["checkpoint_hash"] = _checkpoint_hash(migrated)

    path = store.layout.checkpoint(run_id, new_checkpoint_id)
    created = write_immutable_json(path, migrated)
    if created:
        append_jsonl(store.layout.migration_events(), {
            "event": "checkpoint_migrated",
            "run_id": run_id,
            "source_checkpoint_id": source_checkpoint_id,
            "new_checkpoint_id": new_checkpoint_id,
            "from_schema": "1.0",
            "to_schema": "1.1",
        })
    return migrated
