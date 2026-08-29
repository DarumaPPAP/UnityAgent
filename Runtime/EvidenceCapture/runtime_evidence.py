"""Ephemeral Runtime evidence capture. Durable EvidenceRecord ownership is Persistence."""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def evidence_record(*, evidence_id: str, run_id: str, step_id: str, producer: str, source_type: str, source_ref: str | None, status: str, payload_path: Path | None, provenance: list[str], definition_fingerprint: dict, gate_outcome: dict | None = None) -> dict:
    if status not in {"passed", "failed", "unavailable"}:
        raise ValueError("invalid evidence status")
    payload_ref = None if payload_path is None else payload_path.as_posix()
    payload_hash = None if payload_path is None or not payload_path.is_file() else sha256_file(payload_path)
    return {"schema_version": "1.0", "evidence_id": evidence_id, "run_id": run_id, "step_id": step_id, "producer": producer, "source_type": source_type, "source_ref": source_ref, "status": status, "payload_ref": payload_ref, "hash": payload_hash, "timestamp": datetime.now(timezone.utc).isoformat(), "provenance": provenance, "gate_outcome": gate_outcome, "definition_fingerprint": definition_fingerprint}
