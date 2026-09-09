"""Canonical Persistence write boundary for evaluation-derived Memory proposals.

The writer accepts a serializable proposal and writes only through MemoryStore.
It does not import or call RAG, Runtime, Policy, or an external authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from Persistence.Memory.memory_store import MemoryStore
from Persistence.Store.atomic_store import PersistenceError


_PASS_VALUES = {"pass", "passed", "success", "verified"}
_TARGETS = {"none", "execution_reference", "unityagent_knowledge", "user_policy_candidate"}
_SCOPES = {"project_internal", "portable_artifact", "public_reference"}
_REVIEWS = {"pending", "approved", "rejected", "not_required"}


def _strings(value: Iterable[Any] | Any | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _required(proposal: Mapping[str, Any], field_name: str) -> str:
    value = str(proposal.get(field_name) or "").strip()
    if not value:
        raise PersistenceError("invalid_promotion_proposal", f"promotion proposal requires {field_name}")
    return value


def find_revision_conflicts(store: MemoryStore, proposal: Mapping[str, Any]) -> list[str]:
    """Find prior records for the same normalized query with another source revision."""

    fingerprint = str(proposal.get("query_fingerprint") or "").strip()
    revision = str(proposal.get("source_revision") or "").strip()
    if not fingerprint or not revision:
        return []
    conflicts: list[str] = []
    for record in store.list_accessible("personal_full_control"):
        if str(record.get("query_fingerprint") or "") == fingerprint and str(record.get("source_revision") or "") not in {"", revision}:
            memory_id = str(record.get("memory_id") or "").strip()
            if memory_id and memory_id not in conflicts:
                conflicts.append(memory_id)
    return conflicts


def persist_promotion_proposal(
    store: MemoryStore,
    proposal: Mapping[str, Any],
    *,
    created_at: str | None = None,
    updated_at: str | None = None,
    human_gate_approved: bool = False,
) -> dict[str, Any]:
    """Persist a proposal as an immutable MemoryRecord and evaluate its target gate."""

    if not isinstance(proposal, Mapping):
        raise PersistenceError("invalid_promotion_proposal", "promotion proposal must be an object")
    if str(proposal.get("kind") or "") != "rag_promotion_proposal":
        raise PersistenceError("invalid_promotion_proposal", "unsupported promotion proposal kind")
    proposal_id = _required(proposal, "proposal_id")
    statement = _required(proposal, "statement")
    evaluation_decision = _required(proposal, "evaluation_decision")
    if evaluation_decision.casefold() not in _PASS_VALUES:
        raise PersistenceError("promotion_requires_pass", "only passed evaluation output may enter Memory")
    verification_status = str(proposal.get("verification_status") or "passed").casefold()
    if verification_status not in {"passed", "verified"}:
        raise PersistenceError("promotion_requires_verified", "promotion proposal verification_status must be passed")
    source_evidence_refs = _strings(proposal.get("source_evidence_refs"))
    if not source_evidence_refs:
        raise PersistenceError("promotion_requires_evidence", "promotion proposal requires source_evidence_refs")
    target = str(proposal.get("promotion_target") or "none").strip()
    if target not in _TARGETS:
        raise PersistenceError("invalid_promotion_target", f"unsupported promotion target: {target}")
    requested_scope = str(proposal.get("scope_class") or "project_internal").strip()
    if requested_scope not in _SCOPES:
        raise PersistenceError("invalid_promotion_proposal", f"unsupported scope_class: {requested_scope}")
    proposal_review = str(proposal.get("review_status") or "pending").strip()
    if proposal_review not in _REVIEWS:
        raise PersistenceError("invalid_promotion_proposal", f"unsupported review_status: {proposal_review}")
    if proposal_review == "rejected":
        raise PersistenceError("promotion_rejected", "rejected promotion proposals are not written to Memory")

    now = datetime.now(timezone.utc).isoformat()
    timestamp_created = str(created_at or proposal.get("created_at") or now)
    timestamp_updated = str(updated_at or timestamp_created)
    feedback_id = _required(proposal, "feedback_id")
    conflicts = _strings(proposal.get("conflicts_with"))
    for memory_id in find_revision_conflicts(store, proposal):
        if memory_id not in conflicts:
            conflicts.append(memory_id)
    reviewed = proposal_review == "approved"
    verification_passed = verification_status in {"passed", "verified"}
    confidence = "verified" if reviewed and verification_passed else "probable" if verification_passed else "unverified"
    # A pending proposal is retained for personal review but cannot enter the
    # safe index, even when its requested scope was portable/public.
    effective_scope = requested_scope if reviewed else "project_internal"
    memory_id = str(proposal.get("memory_id") or proposal_id).strip()
    provenance = source_evidence_refs + [f"feedback://{feedback_id}"]
    evaluation_run_id = str(proposal.get("evaluation_run_id") or "").strip()
    evaluation_case_id = str(proposal.get("evaluation_case_id") or "").strip()
    if evaluation_run_id:
        provenance.append(f"eval://run/{evaluation_run_id}")
    record: dict[str, Any] = {
        "schema_version": "1.1",
        "memory_id": memory_id,
        "statement": statement,
        "scope_class": effective_scope,
        "confidence": confidence,
        "source_evidence_refs": source_evidence_refs,
        "source_memory_refs": _strings(proposal.get("source_memory_refs")),
        "created_at": timestamp_created,
        "updated_at": timestamp_updated,
        "applicability": _strings(proposal.get("applicability")),
        "limits": _strings(proposal.get("limits")),
        "layer": "reusable_candidate",
        "provenance": list(dict.fromkeys(provenance)),
        "promotion_target": target,
        "review_status": "approved" if reviewed else proposal_review,
        "supersedes": _strings(proposal.get("supersedes")),
        "conflicts_with": conflicts,
        "repository": proposal.get("repository"),
        "unity_version": proposal.get("unity_version"),
        "platform": proposal.get("platform"),
        "tags": _strings(proposal.get("tags")),
        "experience_feedback_ref": f"feedback://{feedback_id}",
        "source_revision": _required(proposal, "source_revision"),
        "query_fingerprint": _required(proposal, "query_fingerprint"),
        "evaluation_run_id": evaluation_run_id or None,
        "evaluation_case_id": evaluation_case_id or None,
    }
    persisted = store.put(record)
    if target == "none":
        promotion_decision = {
            "memory_id": memory_id,
            "target": target,
            "approved": False,
            "writes_external_authority": False,
            "reasons": ["promotion_target is none"],
        }
    else:
        promotion_decision = store.promote(
            memory_id,
            target,
            human_gate_approved=bool(human_gate_approved),
        )
    return {
        "schema_version": "1.0",
        "proposal_id": proposal_id,
        "memory_id": memory_id,
        "persisted": bool(persisted),
        "memory_record": record,
        "promotion_decision": promotion_decision,
    }


__all__ = ["find_revision_conflicts", "persist_promotion_proposal"]
