"""Split legacy layered-memory records into Evidence candidates and Memory records."""
from __future__ import annotations
from copy import deepcopy
from typing import Any

from Persistence.Store.atomic_store import PersistenceError

L0 = "L0_raw_evidence"
MEMORY_LAYERS = {"L1_atom": "atom", "L2_scenario": "scenario", "L3_reusable_candidate": "reusable_candidate"}


def _raw_id(value: str) -> str:
    normalized = value.replace("\\", "/")
    if not normalized.startswith("Evidence/raw/"):
        raise PersistenceError("legacy_raw_ref_invalid", f"raw ref is outside Evidence/raw: {value}")
    name = normalized.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0]


def normalize_legacy_layered_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(record.get("memory_id")): deepcopy(record) for record in records if record.get("memory_id")}
    if len(by_id) != len(records):
        raise PersistenceError("legacy_memory_invalid", "legacy memory ids must be present and unique")

    evidence_candidates = []
    for memory_id, record in by_id.items():
        if record.get("layer") == L0:
            evidence_candidates.append({
                "evidence_id": memory_id,
                "source_type": str(record.get("source_type") or "legacy_raw_evidence"),
                "source_ref": (record.get("raw_refs") or [None])[0],
                "hash": ("sha256:" + str(record["sha256"])) if record.get("sha256") and not str(record["sha256"]).startswith("sha256:") else record.get("sha256"),
                "verification_status": "unverified",
                "provenance": list(record.get("provenance") or ["legacy-layered-memory"]),
                "legacy_scope_class": record.get("scope_class", "project_internal"),
                "requires_enrichment": ["run_id", "step_id", "producer", "timestamp", "definition_fingerprint"],
            })

    memo: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def evidence_ancestry(memory_id: str) -> set[str]:
        if memory_id in memo:
            return memo[memory_id]
        if memory_id in visiting:
            raise PersistenceError("legacy_memory_cycle", f"legacy memory cycle at {memory_id}")
        visiting.add(memory_id)
        record = by_id.get(memory_id)
        if record is None:
            raise PersistenceError("legacy_memory_reference_missing", f"legacy memory reference missing: {memory_id}")
        layer = record.get("layer")
        result: set[str] = set()
        if layer == L0:
            result.add(memory_id)
        elif layer == "L1_atom":
            for ref in record.get("raw_refs", []):
                raw_id = _raw_id(str(ref))
                if raw_id not in by_id or by_id[raw_id].get("layer") != L0:
                    raise PersistenceError("legacy_memory_reference_missing", f"L1 raw evidence metadata missing: {raw_id}")
                result.add(raw_id)
        elif layer == "L2_scenario":
            for ref in record.get("atom_refs", []):
                result |= evidence_ancestry(str(ref))
        elif layer == "L3_reusable_candidate":
            for ref in record.get("scenario_refs", []):
                result |= evidence_ancestry(str(ref))
        else:
            raise PersistenceError("legacy_memory_layer_unknown", f"unsupported legacy layer: {layer}")
        visiting.remove(memory_id)
        memo[memory_id] = result
        return result

    memory_records = []
    for memory_id, record in by_id.items():
        layer = record.get("layer")
        if layer == L0:
            continue
        if layer not in MEMORY_LAYERS:
            raise PersistenceError("legacy_memory_layer_unknown", f"unsupported legacy layer: {layer}")
        parent_field = {"L1_atom": None, "L2_scenario": "atom_refs", "L3_reusable_candidate": "scenario_refs"}[layer]
        source_memory_refs = [] if parent_field is None else [str(ref) for ref in record.get(parent_field, [])]
        memory_records.append({
            "schema_version": "1.1",
            "memory_id": memory_id,
            "statement": str(record.get("statement") or "").strip(),
            "scope_class": str(record.get("scope_class") or "project_internal"),
            "confidence": str(record.get("confidence") or "unverified"),
            "source_evidence_refs": sorted(evidence_ancestry(memory_id)),
            "source_memory_refs": source_memory_refs,
            "created_at": str(record.get("created_at") or "1970-01-01T00:00:00Z"),
            "updated_at": str(record.get("created_at") or "1970-01-01T00:00:00Z"),
            "applicability": list(record.get("applicability") or []),
            "limits": list(record.get("limits") or []),
            "layer": MEMORY_LAYERS[layer],
            "provenance": list(record.get("provenance") or []),
            "promotion_target": str(record.get("promotion_target") or "none"),
            "review_status": str(record.get("review_status") or "not_required"),
            "supersedes": list(record.get("supersedes") or []),
            "conflicts_with": list(record.get("conflicts_with") or []),
            "repository": record.get("repository"),
            "unity_version": record.get("unity_version"),
            "platform": record.get("platform"),
            "tags": list(record.get("tags") or []),
        })
    return {"evidence_candidates": evidence_candidates, "memory_records": memory_records}
