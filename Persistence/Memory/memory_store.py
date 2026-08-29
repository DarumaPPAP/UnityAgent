"""Durable immutable-oriented MemoryRecord store and promotion gate.

Context retrieval is intentionally not implemented here. Persistence owns
records and lifecycle; Context owns bounded model-input selection.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from Persistence.Store.atomic_store import PersistenceError, append_jsonl, read_json, write_immutable_json
from Persistence.Store.layout import PersistenceLayout

SAFE_SCOPES = {"portable_artifact", "public_reference"}
PROFILES = {"generic_planning", "personal_full_control", "team_safe_import"}
CONFIDENCE = {"verified", "probable", "unverified"}
SCOPE_RANK = {"public_reference": 0, "portable_artifact": 1, "project_internal": 2}


class MemoryStore:
    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

    def put(self, record: dict[str, Any]) -> bool:
        required = {
            "schema_version", "memory_id", "statement", "scope_class", "confidence",
            "source_evidence_refs", "created_at", "updated_at",
        }
        missing = sorted(required - set(record))
        if missing:
            raise PersistenceError("contract_missing_field", f"MemoryRecord missing required fields: {missing}")
        if record.get("schema_version") not in {"1.0", "1.1"}:
            raise PersistenceError("invalid_memory_record", "unsupported MemoryRecord schema_version")
        if record.get("scope_class") not in {"project_internal", *SAFE_SCOPES}:
            raise PersistenceError("invalid_memory_record", "invalid memory scope_class")
        if record.get("confidence") not in CONFIDENCE:
            raise PersistenceError("invalid_memory_record", "invalid memory confidence")
        if not record.get("source_evidence_refs"):
            raise PersistenceError("invalid_memory_record", "MemoryRecord requires source_evidence_refs")

        # Derived Memory may only retain or increase the restriction of its parents.
        # This keeps a project-internal record from being re-labeled portable/public.
        parent_refs = list(record.get("source_memory_refs") or [])
        inherited_rank = -1
        for parent_id in parent_refs:
            parent = self.get(str(parent_id))
            parent_scope = parent.get("scope_class")
            if parent_scope not in SCOPE_RANK:
                raise PersistenceError("invalid_memory_parent", f"invalid parent scope for {parent_id}")
            inherited_rank = max(inherited_rank, SCOPE_RANK[parent_scope])
        if inherited_rank >= 0 and SCOPE_RANK[str(record["scope_class"])] < inherited_rank:
            raise PersistenceError(
                "memory_scope_downgrade_forbidden",
                "derived MemoryRecord scope is less restrictive than a source MemoryRecord",
            )

        path = self.layout.memory(str(record["memory_id"]))
        created = write_immutable_json(path, deepcopy(record))
        if created:
            if record["scope_class"] in SAFE_SCOPES:
                append_jsonl(self.layout.memory_safe_index(), {
                    "memory_id": record["memory_id"],
                    "scope_class": record["scope_class"],
                })
            append_jsonl(self.layout.memory_events(), {
                "event": "memory_created",
                "memory_id": record["memory_id"],
                "scope_class": record["scope_class"],
                "source_evidence_refs": list(record["source_evidence_refs"]),
            })
        return created

    def get(self, memory_id: str) -> dict[str, Any]:
        return read_json(self.layout.memory(memory_id))

    def _safe_ids(self) -> set[str]:
        path = self.layout.memory_safe_index()
        if not path.is_file():
            return set()
        result: set[str] = set()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PersistenceError("safe_index_corrupt", f"safe index line {line_number} is invalid") from exc
            if not isinstance(item, dict) or item.get("scope_class") not in SAFE_SCOPES:
                raise PersistenceError("safe_index_corrupt", "safe index contains invalid scope")
            result.add(str(item.get("memory_id")))
        return result

    def list_accessible(self, execution_profile: str) -> list[dict[str, Any]]:
        if execution_profile not in PROFILES:
            raise PersistenceError("invalid_profile", f"unsupported execution profile: {execution_profile}")
        folder = self.layout.root / "memory" / "records"
        if not folder.is_dir():
            return []
        if execution_profile == "personal_full_control":
            return [read_json(path) for path in sorted(folder.glob("*.json"))]
        safe = self._safe_ids()
        result = []
        for memory_id in sorted(safe):
            record = self.get(memory_id)
            if record.get("scope_class") not in SAFE_SCOPES:
                raise PersistenceError("safe_index_mismatch", f"safe index scope mismatch for {memory_id}")
            result.append(record)
        return result

    def promote(self, memory_id: str, target: str, *, human_gate_approved: bool = False) -> dict[str, Any]:
        record = self.get(memory_id)
        allowed = {"execution_reference", "unityagent_knowledge", "user_policy_candidate"}
        if target not in allowed:
            raise PersistenceError("invalid_promotion_target", f"unsupported promotion target: {target}")
        reasons: list[str] = []
        if record.get("review_status") != "approved":
            reasons.append("memory review_status must be approved")
        if target in {"unityagent_knowledge", "user_policy_candidate"} and record.get("confidence") != "verified":
            reasons.append(f"{target} requires verified confidence")
        if target == "user_policy_candidate" and not human_gate_approved:
            reasons.append("user_policy_candidate requires explicit Human Gate approval")
        decision = {
            "memory_id": memory_id,
            "target": target,
            "approved": not reasons,
            "writes_external_authority": False,
            "reasons": reasons,
        }
        append_jsonl(self.layout.memory_events(), {"event": "promotion_evaluated", **decision})
        return decision
