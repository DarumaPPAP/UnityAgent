"""Convert Runtime ExecutionEvidence facts to durable EvidenceRecord facts."""
from __future__ import annotations
from copy import deepcopy
from typing import Any

from Persistence.Store.atomic_store import PersistenceError

STATUS_MAP = {"passed": "passed", "failed": "failed", "unavailable": "unavailable"}


def from_runtime_execution_evidence(record: dict[str, Any]) -> dict[str, Any]:
    status = record.get("status")
    if status not in STATUS_MAP:
        raise PersistenceError("runtime_evidence_status_invalid", f"unsupported Runtime evidence status: {status}")
    required = {
        "evidence_id", "run_id", "step_id", "producer", "source_type", "source_ref",
        "payload_ref", "hash", "timestamp", "provenance", "definition_fingerprint",
    }
    missing = sorted(required - set(record))
    if missing:
        raise PersistenceError("runtime_evidence_contract_incomplete", f"missing Runtime evidence fields: {missing}")
    return {
        "schema_version": "1.1",
        "evidence_id": record["evidence_id"],
        "run_id": record["run_id"],
        "step_id": record["step_id"],
        "source_type": record["source_type"],
        "source_ref": record["source_ref"],
        "timestamp": record["timestamp"],
        "hash": record["hash"],
        "producer": record["producer"],
        "verification_status": STATUS_MAP[status],
        "provenance": list(record["provenance"]),
        "payload_ref": record["payload_ref"],
        "gate_outcome": deepcopy(record.get("gate_outcome")),
        "definition_fingerprint": deepcopy(record["definition_fingerprint"]),
    }
