"""Durable approval decisions and revocation epochs."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from Persistence.Store.atomic_store import PersistenceError, atomic_write_json, read_json
from Persistence.Store.layout import PersistenceLayout


class ApprovalDecisionStore:
    """Persistence owner for the trusted ApprovalDecision lookup boundary."""

    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

    def register(self, decision: Any) -> None:
        payload = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision)
        approval_id = str(payload.get("approval_decision_id") or "")
        if not approval_id:
            raise PersistenceError("invalid_approval_decision", "approval_decision_id is required")
        atomic_write_json(
            self.layout.approval_decision(approval_id),
            {"schema_version": "1.1", "decision": deepcopy(payload), "current_revocation_epoch": int(payload.get("revocation_epoch", 0))},
        )

    def get(self, approval_decision_id: str) -> dict[str, Any]:
        record = read_json(self.layout.approval_decision(approval_decision_id))
        if record.get("schema_version") != "1.1" or not isinstance(record.get("decision"), dict):
            raise PersistenceError("invalid_approval_decision", "approval decision record is corrupt")
        return record

    def revoke(self, approval_decision_id: str) -> int:
        record = self.get(approval_decision_id)
        current = int(record.get("current_revocation_epoch", record["decision"].get("revocation_epoch", 0))) + 1
        record["current_revocation_epoch"] = current
        atomic_write_json(self.layout.approval_decision(approval_decision_id), record)
        return current
