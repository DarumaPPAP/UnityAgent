"""Convert Runtime ExecutionEvidence facts to durable EvidenceRecord facts."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from Persistence.Store.atomic_store import PersistenceError

STATUS_MAP = {
    "passed": "passed",
    "failed": "failed",
    "unavailable": "unavailable",
    "unverified": "unverified",
}
V11_REQUIRED = {
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


def _common_required(record: dict[str, Any]) -> None:
    status = record.get("status")
    if status not in STATUS_MAP:
        raise PersistenceError(
            "runtime_evidence_status_invalid",
            f"unsupported Runtime evidence status: {status}",
        )
    required = {
        "evidence_id",
        "run_id",
        "step_id",
        "producer",
        "source_type",
        "source_ref",
        "payload_ref",
        "hash",
        "timestamp",
        "provenance",
        "definition_fingerprint",
    }
    missing = sorted(required - set(record))
    if missing:
        raise PersistenceError(
            "runtime_evidence_contract_incomplete",
            f"missing Runtime evidence fields: {missing}",
        )


def _runtime_schema_version(record: dict[str, Any]) -> str:
    schema_version = record.get("schema_version")
    if schema_version is None:
        # Pre-versioned Runtime/Persistence bridge records existed before the
        # canonical ExecutionEvidence schema was enforced. Preserve that exact
        # legacy shape, but never guess v1.1 when any v1.1-only field is present.
        if V11_REQUIRED.intersection(record):
            raise PersistenceError(
                "runtime_evidence_schema_invalid",
                "schema_version is required when Runtime Evidence v1.1 fields are present",
            )
        return "1.0"
    if schema_version not in {"1.0", "1.1"}:
        raise PersistenceError(
            "runtime_evidence_schema_invalid",
            f"unsupported Runtime evidence schema_version: {schema_version}",
        )
    return str(schema_version)


def from_runtime_execution_evidence(record: dict[str, Any]) -> dict[str, Any]:
    _common_required(record)
    schema_version = _runtime_schema_version(record)
    if schema_version == "1.0":
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
            "verification_status": STATUS_MAP[record["status"]],
            "provenance": list(record["provenance"]),
            "payload_ref": record["payload_ref"],
            "gate_outcome": deepcopy(record.get("gate_outcome")),
            "definition_fingerprint": deepcopy(record["definition_fingerprint"]),
        }

    missing = sorted(V11_REQUIRED - set(record))
    if missing:
        raise PersistenceError(
            "runtime_evidence_contract_incomplete",
            f"missing Runtime Evidence v1.1 fields: {missing}",
        )
    if record.get("durability") != "current_run":
        raise PersistenceError(
            "runtime_evidence_durability_invalid",
            "Runtime evidence must be current_run before Persistence append",
        )

    return {
        "schema_version": "1.2",
        "evidence_id": record["evidence_id"],
        "run_id": record["run_id"],
        "step_id": record["step_id"],
        "source_type": record["source_type"],
        "source_ref": record["source_ref"],
        "timestamp": record["timestamp"],
        "hash": record["hash"],
        "producer": record["producer"],
        "verification_status": STATUS_MAP[record["status"]],
        "provenance": list(record["provenance"]),
        "payload_ref": record["payload_ref"],
        "gate_outcome": deepcopy(record.get("gate_outcome")),
        "definition_fingerprint": deepcopy(record["definition_fingerprint"]),
        "capability": record["capability"],
        "provider_ref": record["provider_ref"],
        "project_root": record["project_root"],
        "environment": deepcopy(record["environment"]),
        "target": deepcopy(record["target"]),
        "safety_strength": int(record["safety_strength"]),
        "evidence_strength": int(record["evidence_strength"]),
        "completion": record["completion"],
        "observation_state": record["observation_state"],
        "failure_class": record["failure_class"],
        "observed_evidence": list(record["observed_evidence"]),
        "required_evidence": list(record["required_evidence"]),
        "raw_refs": list(record["raw_refs"]),
        "mutation_provenance": deepcopy(record["mutation_provenance"]),
        "latency_ms": record["latency_ms"],
        "fallback_from": record["fallback_from"],
        "durability": "durable",
    }


def append_runtime_execution_evidence(store: Any, record: dict[str, Any]) -> dict[str, Any]:
    """Append once through the Persistence owner and return durable append facts.

    Conversion alone does not make Evidence durable. Durability is established
    only after the store accepts an immutable record (or confirms an identical
    idempotent record already exists).
    """
    durable = from_runtime_execution_evidence(record)
    created = bool(store.append(durable))
    persisted = store.get(str(durable["evidence_id"]))
    if persisted != durable:
        raise PersistenceError(
            "durable_evidence_mismatch",
            "Persistence read-back does not match the appended EvidenceRecord",
        )
    return {
        "created": created,
        "durable": True,
        "evidence_id": durable["evidence_id"],
        "record": persisted,
    }
