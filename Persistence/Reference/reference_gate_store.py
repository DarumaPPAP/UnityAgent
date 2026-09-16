"""Atomic persistence for v1.1 reservation and idempotency state."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from Persistence.Store.atomic_store import atomic_write_json, read_json, PersistenceError
from Persistence.Store.layout import PersistenceLayout


class ReferenceGateStore:
    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

    def load_reservations(self, run_id: str) -> dict[str, Any]:
        try:
            return read_json(self.layout.reference_reservations(run_id))
        except PersistenceError as exc:
            if exc.code == "record_not_found":
                return {"schema_version": "1.1", "run_id": run_id, "records": {}}
            raise

    def save_reservations(self, run_id: str, records: dict[str, Any]) -> None:
        atomic_write_json(self.layout.reference_reservations(run_id), {"schema_version": "1.1", "run_id": run_id, "records": deepcopy(records)})

    def load_idempotency(self, run_id: str) -> dict[str, Any]:
        try:
            return read_json(self.layout.reference_idempotency(run_id))
        except PersistenceError as exc:
            if exc.code == "record_not_found":
                return {"schema_version": "1.1", "run_id": run_id, "records": {}}
            raise

    def save_idempotency(self, run_id: str, records: dict[str, Any]) -> None:
        atomic_write_json(self.layout.reference_idempotency(run_id), {"schema_version": "1.1", "run_id": run_id, "records": deepcopy(records)})
