"""Durable approval decisions and revocation epochs."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from unityagent.persistence.store.atomic_store import PersistenceError, atomic_write_json, exclusive_file_lock, read_json
from unityagent.persistence.store.layout import PersistenceLayout


class ApprovalDecisionStore:
    """Persistence owner for the trusted ApprovalDecision lookup boundary."""

    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

    def register(self, decision: Any) -> None:
        payload = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision)
        approval_id = str(payload.get("approval_decision_id") or "")
        if not approval_id:
            raise PersistenceError("invalid_approval_decision", "approval_decision_id is required")
        path = self.layout.approval_decision(approval_id)
        with exclusive_file_lock(path.with_suffix(".lock")):
            record = self.get(approval_id) if path.exists() else {}
            epoch = max(int(record.get("current_revocation_epoch", 0)), int(payload.get("revocation_epoch", 0)))
            # 再登録によって取消や単回消費を失わず、既存承認の再利用を防ぐ。
            record.update({"schema_version": "1.1", "decision": deepcopy(payload), "current_revocation_epoch": epoch})
            atomic_write_json(path, record)

    def get(self, approval_decision_id: str) -> dict[str, Any]:
        record = read_json(self.layout.approval_decision(approval_decision_id))
        if record.get("schema_version") != "1.1" or not isinstance(record.get("decision"), dict):
            raise PersistenceError("invalid_approval_decision", "approval decision record is corrupt")
        return record

    def revoke(self, approval_decision_id: str) -> int:
        path = self.layout.approval_decision(approval_decision_id)
        with exclusive_file_lock(path.with_suffix(".lock")):
            record = self.get(approval_decision_id)
            current = int(record.get("current_revocation_epoch", record["decision"].get("revocation_epoch", 0))) + 1
            record["current_revocation_epoch"] = current
            atomic_write_json(path, record)
            return current

    def bind_artist_plan(self, approval_decision_id: str, binding: dict[str, Any]) -> None:
        """Control Planeがレビュー済みPlanを承認へ束縛する。Transportは呼び出さない。"""
        path = self.layout.approval_decision(approval_decision_id)
        with exclusive_file_lock(path.with_suffix(".lock")):
            record = self.get(approval_decision_id)
            if binding.get("approvalDigest") != record["decision"].get("decision_digest"):
                raise PersistenceError("approval_binding_mismatch", "reviewed plan belongs to a different decision")
            previous = record.get("artist_plan")
            if previous is not None and previous != binding:
                raise PersistenceError("immutable_record_conflict", "reviewed Artist plan cannot be replaced")
            record["artist_plan"] = deepcopy(binding)
            atomic_write_json(path, record)

    def consume_artist_plan(self, approval_decision_id: str, binding: dict[str, Any], *, validate, reservation_id: str) -> None:
        """取消と同じOS lock内で再検証し、実行開始を永続的に一度だけ確定する。"""
        path = self.layout.approval_decision(approval_decision_id)
        with exclusive_file_lock(path.with_suffix(".lock")):
            record = self.get(approval_decision_id)
            if record.get("artist_plan") != binding or binding.get("approvalDigest") != record["decision"].get("decision_digest"):
                raise PersistenceError("approval_binding_mismatch", "reviewed Artist plan was not found")
            if record.get("artist_consumption") is not None:
                raise PersistenceError("approval_already_used", "Artist approval has already started execution")
            validate()
            record["artist_consumption"] = {"reservation_id": reservation_id, "binding": deepcopy(binding), "state": "execution_started"}
            # この保存が認可の確定点。以後の通信断でも承認を未使用へ戻さない。
            atomic_write_json(path, record)
