"""Append-oriented immutable EvidenceRecord store."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from Persistence.Contracts.definition_fingerprint import validate_definition_fingerprint
from Persistence.Store.atomic_store import (
    PersistenceError,
    append_jsonl,
    read_json,
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
    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

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

        path = self.layout.evidence(str(record["evidence_id"]))
        created = write_immutable_json(path, deepcopy(record))
        if created:
            append_jsonl(
                self.layout.evidence_events(),
                {
                    "event": "evidence_appended",
                    "evidence_id": record["evidence_id"],
                    "run_id": record["run_id"],
                    "record_hash": sha256_json(record),
                },
            )
        return created

    def get(self, evidence_id: str) -> dict[str, Any]:
        return read_json(self.layout.evidence(evidence_id))
