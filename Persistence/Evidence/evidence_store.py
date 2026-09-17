"""Append-oriented immutable EvidenceRecord store."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
from typing import Any

from Persistence.Contracts.definition_fingerprint import validate_definition_fingerprint
from Persistence.Store.atomic_store import (
    PersistenceError,
    append_jsonl,
    read_json,
    exclusive_file_lock,
    safe_id,
    sha256_json,
    write_immutable_json,
)
from Persistence.Store.layout import PersistenceLayout

VERIFICATION = {"passed", "failed", "unavailable", "unverified"}
V12_REQUIRED = {
    "capability",
    "provider_ref",
    "project_root",
    "environment",
    "target",
    "safety_strength",
    "evidence_strength",
    "completion",
    "observation_state",
    "failure_class",
    "observed_evidence",
    "required_evidence",
    "raw_refs",
    "mutation_provenance",
    "latency_ms",
    "fallback_from",
    "durability",
}


class EvidenceStore:
    _lock_guard = threading.Lock()
    _append_locks: dict[str, threading.RLock] = {}

    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)
        key = str(self.layout.root)
        with self._lock_guard:
            self._append_lock = self._append_locks.setdefault(key, threading.RLock())

    def append(self, record: dict[str, Any]) -> bool:
        required = {
            "schema_version",
            "evidence_id",
            "run_id",
            "step_id",
            "source_type",
            "source_ref",
            "timestamp",
            "hash",
            "producer",
            "verification_status",
            "provenance",
            "definition_fingerprint",
        }
        missing = sorted(required - set(record))
        if missing:
            raise PersistenceError(
                "contract_missing_field",
                f"EvidenceRecord missing required fields: {missing}",
            )
        if record.get("schema_version") not in {"1.0", "1.1", "1.2"}:
            raise PersistenceError(
                "invalid_evidence_record",
                "unsupported EvidenceRecord schema_version",
            )
        if record.get("verification_status") not in VERIFICATION:
            raise PersistenceError(
                "invalid_evidence_record",
                "invalid verification_status",
            )
        if not record.get("provenance"):
            raise PersistenceError(
                "invalid_evidence_record",
                "EvidenceRecord provenance must not be empty",
            )
        if record.get("schema_version") == "1.2":
            missing_v12 = sorted(V12_REQUIRED - set(record))
            if missing_v12:
                raise PersistenceError(
                    "invalid_evidence_record",
                    f"EvidenceRecord v1.2 missing fields: {missing_v12}",
                )
            if record.get("durability") != "durable":
                raise PersistenceError(
                    "invalid_evidence_record",
                    "EvidenceRecord v1.2 durability must be durable",
                )
            for strength in ("safety_strength", "evidence_strength"):
                value = record.get(strength)
                if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 5:
                    raise PersistenceError(
                        "invalid_evidence_record",
                        f"{strength} must be an integer in range 0..5",
                    )
        validate_definition_fingerprint(record.get("definition_fingerprint"))

        if not isinstance(record.get("run_id"), str):
            raise PersistenceError(
                "invalid_evidence_record",
                "EvidenceRecord run_id must be a string identifier",
            )
        run_id = safe_id(record["run_id"], "run_id")
        if run_id != record["run_id"]:
            raise PersistenceError(
                "invalid_evidence_record",
                "EvidenceRecord run_id must use its canonical identifier form",
            )

        if not isinstance(record.get("evidence_id"), str):
            raise PersistenceError(
                "invalid_evidence_record",
                "EvidenceRecord evidence_id must be a string identifier",
            )
        evidence_id = safe_id(record["evidence_id"], "evidence_id")
        if evidence_id != record["evidence_id"]:
            raise PersistenceError(
                "invalid_evidence_record",
                "EvidenceRecord evidence_id must use its canonical identifier form",
            )

        path = self.layout.evidence(evidence_id)
        with self._append_lock, exclusive_file_lock(self.layout.evidence_lock(run_id)):
            created = write_immutable_json(path, deepcopy(record))
            if created:
                events = self._read_events(run_id)
                previous_event_hash = events[-1].get("event_hash") if events else None
                event_material = {
                    "event": "evidence_appended",
                    "evidence_id": record["evidence_id"],
                    "run_id": record["run_id"],
                    "record_hash": sha256_json(record),
                    "previous_event_hash": previous_event_hash,
                }
                append_jsonl(
                    self.layout.evidence_events(run_id),
                    {**event_material, "event_hash": sha256_json(event_material)},
                )
            return created

    def get(self, evidence_id: str) -> dict[str, Any]:
        # Resolve through safe_id in layout.evidence; never allow a caller to
        # turn an evidence reference into an arbitrary filesystem path.
        return read_json(self.layout.evidence(evidence_id))

    def _read_events(self, run_id: str | None = None) -> list[dict[str, Any]]:
        path = self.layout.evidence_events(run_id)
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise PersistenceError("record_corrupt", f"cannot read evidence event log: {path}: {exc}") from exc
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PersistenceError("record_corrupt", f"invalid evidence event at line {line_number}") from exc
            if not isinstance(value, dict):
                raise PersistenceError("record_corrupt", f"evidence event at line {line_number} is not an object")
            events.append(value)
        return events

    def verify_event_chain(self, *, expected_run_id: str | None = None) -> list[dict[str, Any]]:
        """Verify every event hash and its predecessor binding before reuse."""
        events = self._read_events(expected_run_id)
        previous: str | None = None
        for index, event in enumerate(events, start=1):
            required = {"event", "evidence_id", "run_id", "record_hash", "previous_event_hash", "event_hash"}
            if not required.issubset(event):
                raise PersistenceError("evidence_event_tampered", f"evidence event {index} has an incomplete hash envelope")
            if expected_run_id is not None and event.get("run_id") != expected_run_id:
                raise PersistenceError("run_scope_mismatch", f"evidence event {index} belongs to another run")
            material = {key: event[key] for key in required if key != "event_hash"}
            if event.get("previous_event_hash") != previous:
                raise PersistenceError("evidence_event_tampered", f"evidence event {index} predecessor mismatch")
            if event.get("event_hash") != sha256_json(material):
                raise PersistenceError("evidence_event_tampered", f"evidence event {index} hash mismatch")
            previous = str(event["event_hash"])
        return events

    def verify_record(self, evidence_id: str, *, expected_run_id: str | None = None) -> dict[str, Any]:
        """Re-read and verify immutable record, event-chain, and run binding."""
        record = self.get(evidence_id)
        if record.get("evidence_id") != evidence_id:
            raise PersistenceError("evidence_tampered", "evidence id does not match its filename/reference")
        if expected_run_id is not None and record.get("run_id") != expected_run_id:
            raise PersistenceError("run_scope_mismatch", "evidence record belongs to another run")
        events = self.verify_event_chain(expected_run_id=record.get("run_id"))
        record_hash = sha256_json(record)
        matches = [event for event in events if event.get("evidence_id") == evidence_id]
        if len(matches) != 1:
            raise PersistenceError("evidence_tampered", "evidence record does not have exactly one event binding")
        event = matches[0]
        if event.get("run_id") != record.get("run_id") or event.get("record_hash") != record_hash:
            raise PersistenceError("evidence_tampered", "evidence event does not bind the persisted record")
        return record

    @staticmethod
    def verify_asset(path: str | Path, expected_digest: str, *, expected_bytes: int | None = None) -> dict[str, Any]:
        """Verify a capture asset digest without accepting metadata-only proof."""
        if not isinstance(expected_digest, str) or not expected_digest:
            raise PersistenceError("asset_unverified", "capture asset digest is missing")
        candidate = Path(path).expanduser().resolve(strict=False)
        if not candidate.is_file():
            raise PersistenceError("asset_unverified", f"capture asset does not exist: {candidate}")
        try:
            data = candidate.read_bytes()
        except OSError as exc:
            raise PersistenceError("asset_unverified", f"capture asset could not be read: {candidate}") from exc
        actual_hex = hashlib.sha256(data).hexdigest()
        actual = f"sha256:{actual_hex}"
        accepted = {actual, actual_hex}
        if expected_digest not in accepted:
            raise PersistenceError("asset_tampered", "capture asset digest mismatch")
        if expected_bytes is not None and expected_bytes != len(data):
            raise PersistenceError("asset_tampered", "capture asset byte count mismatch")
        return {"path": str(candidate), "bytes": len(data), "sha256": actual_hex}
