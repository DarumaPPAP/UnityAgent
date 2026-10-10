"""Normalize one observed verification fact without grading task quality."""
from __future__ import annotations
ALLOWED_STATUSES = {"passed", "failed", "unavailable"}
ALLOWED_REQUIREMENTS = {"required", "conditional", "informational", "not_applicable", "unknown"}


def gate_observation(gate_id: str, status: str, *, requirement: str = "unknown", evidence_refs: list[str] | None = None, detail: str | None = None) -> dict:
    if not gate_id:
        raise ValueError("gate_id is required")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid gate status: {status}")
    if requirement not in ALLOWED_REQUIREMENTS:
        raise ValueError(f"invalid gate requirement: {requirement}")
    return {"gate_id": gate_id, "requirement": requirement, "status": status, "evidence_refs": list(evidence_refs or []), "detail": detail}
