"""Atomic, run-scoped persistence for the Reference Implementation gate."""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from typing import Any, Mapping

from Persistence.Store.atomic_store import atomic_write_json, exclusive_file_lock, read_json, PersistenceError
from Persistence.Store.layout import PersistenceLayout


class ReferenceGateStore:
    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

    @contextmanager
    def locked(self, run_id: str):
        """Serialize a read/modify/write gate transition for one run."""
        with exclusive_file_lock(self.layout.reference_lock(run_id)):
            yield

    @staticmethod
    def _validate_run_envelope(run_id: str, value: Any, *, kind: str) -> dict[str, Any]:
        if not isinstance(run_id, str) or not run_id:
            raise PersistenceError("invalid_run_id", "run_id must be a non-empty string")
        if not isinstance(value, Mapping):
            raise PersistenceError("invalid_run_envelope", f"{kind} persistence must be an object")
        if value.get("schema_version") != "1.2":
            raise PersistenceError("invalid_run_envelope", f"{kind} persistence schema is not canonical")
        if value.get("run_id") != run_id:
            raise PersistenceError("run_scope_mismatch", f"{kind} persistence is bound to another run")
        records = value.get("records")
        if not isinstance(records, Mapping):
            raise PersistenceError("invalid_run_envelope", f"{kind} records must be an object")
        prefix = f"run={run_id}:"
        for key, record in records.items():
            if not isinstance(key, str) or not key.startswith(prefix):
                raise PersistenceError("run_scope_mismatch", f"{kind} record key is outside run {run_id}")
            if not isinstance(record, Mapping) or record.get("run_id") != run_id:
                raise PersistenceError("run_scope_mismatch", f"{kind} record is outside run {run_id}")
        return deepcopy(dict(value))

    def load_reservations(self, run_id: str) -> dict[str, Any]:
        try:
            value = read_json(self.layout.reference_reservations(run_id))
            return self._validate_run_envelope(run_id, value, kind="reservation")
        except PersistenceError as exc:
            if exc.code == "record_not_found":
                return {"schema_version": "1.2", "run_id": run_id, "records": {}}
            raise

    def save_reservations(self, run_id: str, records: dict[str, Any]) -> None:
        envelope = self._validate_run_envelope(
            run_id,
            {"schema_version": "1.2", "run_id": run_id, "records": records},
            kind="reservation",
        )
        atomic_write_json(self.layout.reference_reservations(run_id), envelope)

    def load_idempotency(self, run_id: str) -> dict[str, Any]:
        try:
            value = read_json(self.layout.reference_idempotency(run_id))
            return self._validate_run_envelope(run_id, value, kind="idempotency")
        except PersistenceError as exc:
            if exc.code == "record_not_found":
                return {"schema_version": "1.2", "run_id": run_id, "records": {}}
            raise

    def save_idempotency(self, run_id: str, records: dict[str, Any]) -> None:
        envelope = self._validate_run_envelope(
            run_id,
            {"schema_version": "1.2", "run_id": run_id, "records": records},
            kind="idempotency",
        )
        atomic_write_json(self.layout.reference_idempotency(run_id), envelope)

    def save_manifest(self, run_id: str, manifest: Mapping[str, Any]) -> None:
        if not isinstance(manifest, Mapping):
            raise PersistenceError("invalid_manifest", "reference manifest must be an object")
        if manifest.get("schema_version") != "1.2":
            raise PersistenceError("invalid_manifest", "reference manifest schema is not canonical")
        if manifest.get("run_id") != run_id:
            raise PersistenceError("run_scope_mismatch", "reference manifest is bound to another run")
        atomic_write_json(self.layout.reference_manifest(run_id), deepcopy(dict(manifest)))

    def load_manifest(self, run_id: str) -> dict[str, Any]:
        value = read_json(self.layout.reference_manifest(run_id))
        if not isinstance(value, Mapping) or value.get("schema_version") != "1.2":
            raise PersistenceError("invalid_manifest", "reference manifest schema is not canonical")
        if value.get("run_id") != run_id:
            raise PersistenceError("run_scope_mismatch", "reference manifest is bound to another run")
        return deepcopy(dict(value))
