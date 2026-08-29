"""Atomic durable SessionRecord store."""
from __future__ import annotations
from copy import deepcopy
from typing import Any

from Persistence.Store.atomic_store import PersistenceError, atomic_write_json, read_json
from Persistence.Store.layout import PersistenceLayout


class SessionStore:
    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

    def save(self, record: dict[str, Any]) -> None:
        required = {"schema_version", "session_id", "created_at", "updated_at", "active_run_ids", "last_checkpoint_ref"}
        missing = sorted(required - set(record))
        if missing:
            raise PersistenceError("contract_missing_field", f"SessionRecord missing required fields: {missing}")
        if record.get("schema_version") != "1.0":
            raise PersistenceError("invalid_session_record", "unsupported SessionRecord schema_version")
        path = self.layout.session(str(record["session_id"]))
        if path.exists():
            current = read_json(path)
            if current.get("session_id") != record.get("session_id") or current.get("created_at") != record.get("created_at"):
                raise PersistenceError("session_identity_conflict", "SessionRecord identity/created_at cannot change")
        atomic_write_json(path, deepcopy(record))

    def get(self, session_id: str) -> dict[str, Any]:
        return read_json(self.layout.session(session_id))
