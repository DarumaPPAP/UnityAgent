"""Deterministic Runtime gates for the Camera FOV reference path."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
from typing import Any, Callable, Mapping

from Persistence.Evidence.runtime_adapter import append_runtime_execution_evidence
from Persistence.Reference.reference_gate_store import ReferenceGateStore

from .authority import BudgetExceeded, RuntimeBudgetLedger, utc_now
from .canonicalization import digest_for, sha256_jcs
from .contracts import (
    ALLOWED_EVIDENCE,
    ApprovalDecision,
    CompletionProof,
    CompletionDecision,
    ContractValidationError,
    EvidenceRecord,
    ProviderResult,
    SurfaceGrant,
    TaskContract,
    TypedAction,
)


class CrossContractValidator:
    """Revalidates every cross-binding at the last trusted boundary."""

    def __init__(self, approval_resolver: Any | None = None) -> None:
        self.approval_resolver = approval_resolver

    def validate(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        grant: SurfaceGrant,
        action: TypedAction,
        now: datetime | None = None,
        approval_resolver: Any | None = None,
    ) -> None:
        TaskContract.from_dict(task.to_dict())
        ApprovalDecision.from_dict(approval.to_dict())
        SurfaceGrant.from_dict(grant.to_dict())
        TypedAction.from_dict(action.to_dict())
        if approval.task_id != task.task_id or approval.run_id != task.run_id:
            raise ContractValidationError("ApprovalDecision task/run binding mismatch")
        if approval.project != task.project or approval.project_fingerprint != task.project_fingerprint:
            raise ContractValidationError("ApprovalDecision project binding mismatch")
        if approval.contract_digest != task.contract_digest:
            raise ContractValidationError("ApprovalDecision contract digest mismatch")
        if approval.scope != task.scope:
            raise ContractValidationError("ApprovalDecision scope differs from TaskContract")
        if grant.audience != "unity_artist" or grant.task_id != task.task_id or grant.run_id != task.run_id:
            raise ContractValidationError("SurfaceGrant audience/task/run binding mismatch")
        if grant.project != task.project or grant.project_fingerprint != task.project_fingerprint:
            raise ContractValidationError("SurfaceGrant project binding mismatch")
        if grant.contract_digest != task.contract_digest or grant.approval_digest != approval.decision_digest:
            raise ContractValidationError("SurfaceGrant digest binding mismatch")
        if approval.status != "active" or approval.human_review != "approved":
            raise ContractValidationError("approval is not active and human-approved")
        resolver = approval_resolver or self.approval_resolver
        if resolver is not None:
            trusted = resolver.resolve(approval.approval_decision_id, task=task, now=now)
            if trusted.decision_digest != approval.decision_digest or trusted.revocation_epoch != approval.revocation_epoch:
                raise ContractValidationError("ApprovalDecision is stale or has been revoked")
        if datetime.fromisoformat(grant.expires_at.replace("Z", "+00:00")) <= (now or utc_now()):
            raise ContractValidationError("SurfaceGrant has expired")
        if action.task_id != task.task_id or action.run_id != task.run_id:
            raise ContractValidationError("TypedAction task/run binding mismatch")
        if action.contract_digest != task.contract_digest or action.approval_decision_id != approval.approval_decision_id:
            raise ContractValidationError("TypedAction contract/approval binding mismatch")
        if action.approval_digest != approval.decision_digest or action.grant_id != grant.grant_id or action.grant_digest != grant.grant_digest:
            raise ContractValidationError("TypedAction digest/grant binding mismatch")
        if action.project != task.project or action.project_fingerprint != task.project_fingerprint:
            raise ContractValidationError("TypedAction project binding mismatch")
        target_guid = task.scope["target_guids"][0]
        if action.target["guid"] != target_guid or action.target["component_type"] != "UnityEngine.Camera":
            raise ContractValidationError("TypedAction target is outside the approved scope")
        if action.property_path not in task.scope["property_paths"] or action.property_path != "Camera.fieldOfView":
            raise ContractValidationError("TypedAction property is outside the approved scope")
        if action.mutation_channel not in task.scope["mutation_channels"]:
            raise ContractValidationError("TypedAction mutation channel is outside the approved scope")
        if action.capability not in grant.capabilities or action.capability != approval.capability:
            raise ContractValidationError("TypedAction capability is not granted")
        if not approval.parameter_envelope["min"] <= action.value <= approval.parameter_envelope["max"]:
            raise ContractValidationError("TypedAction value is outside the approved parameter envelope")
        if any(item not in task.required_evidence for item in action.additional_required_evidence):
            raise ContractValidationError("TypedAction requested evidence outside TaskContract")


class ReservationConflict(RuntimeError):
    """Another action owns the mutation reservation."""


class ReservationState:
    NONE = "NONE"
    PREPARED = "PREPARED"
    APPLIED = "APPLIED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"
    IN_DOUBT = "IN_DOUBT"


@dataclass
class ReservationRecord:
    key: str
    action_id: str
    action_digest: str
    state: str
    expected_revision: str
    provider_result: dict[str, Any] | None = None
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "action_id": self.action_id, "action_digest": self.action_digest,
            "state": self.state, "expected_revision": self.expected_revision,
            "provider_result": self.provider_result, "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReservationRecord":
        evidence_ids = value.get("evidence_ids", [])
        if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
            raise ContractValidationError("reservation evidence_ids are invalid")
        return cls(
            key=str(value["key"]),
            action_id=str(value["action_id"]),
            action_digest=str(value["action_digest"]),
            state=str(value["state"]),
            expected_revision=str(value["expected_revision"]),
            provider_result=dict(value["provider_result"]) if isinstance(value.get("provider_result"), Mapping) else None,
            evidence_ids=list(evidence_ids),
        )


class ActionReservationStore:
    """Thread-safe reservation state machine for one target/property key."""

    def __init__(self, persistence: ReferenceGateStore | None = None, *, run_id: str | None = None) -> None:
        self._records: dict[str, ReservationRecord] = {}
        self._lock = threading.RLock()
        self.persistence = persistence
        self.run_id = run_id
        self._loaded_runs: set[str] = set()

    @staticmethod
    def _key(action: TypedAction) -> str:
        return f"{action.project_fingerprint}:{action.target['guid']}:UnityEngine.Camera:{action.property_path}"

    def _ensure_loaded(self, run_id: str) -> None:
        if self.persistence is None or run_id in self._loaded_runs:
            return
        data = self.persistence.load_reservations(run_id)
        self._records.update({key: ReservationRecord.from_dict(item) for key, item in (data.get("records") or {}).items()})
        self._loaded_runs.add(run_id)

    def _persist(self, run_id: str) -> None:
        if self.persistence is not None:
            self.persistence.save_reservations(run_id, {key: record.to_dict() for key, record in self._records.items()})

    def reserve(self, action: TypedAction) -> ReservationRecord:
        key = self._key(action)
        with self._lock:
            self._ensure_loaded(action.run_id)
            current = self._records.get(key)
            if current is not None:
                if current.action_digest != action.action_digest:
                    raise ReservationConflict("reservation key is bound to a different action digest")
                if current.state == ReservationState.COMMITTED:
                    return current
                raise ReservationConflict(f"reservation is already {current.state}")
            record = ReservationRecord(key, action.action_id, action.action_digest, ReservationState.PREPARED, action.expected_revision)
            self._records[key] = record
            self._persist(action.run_id)
            return record

    def get(self, action: TypedAction) -> ReservationRecord | None:
        key = self._key(action)
        with self._lock:
            self._ensure_loaded(action.run_id)
            return self._records.get(key)

    def mark_applied(self, action: TypedAction, result: ProviderResult) -> None:
        with self._lock:
            record = self._require(action)
            if record.state != ReservationState.PREPARED:
                raise ReservationConflict(f"cannot mark {record.state} as APPLIED")
            record.provider_result = result.to_dict()
            record.state = ReservationState.APPLIED
            self._persist(action.run_id)

    def commit(self, action: TypedAction) -> ReservationRecord:
        with self._lock:
            record = self._require(action)
            if record.state == ReservationState.COMMITTED:
                return record
            if record.state not in {ReservationState.APPLIED, ReservationState.IN_DOUBT}:
                raise ReservationConflict(f"cannot commit {record.state}")
            record.state = ReservationState.COMMITTED
            self._persist(action.run_id)
            return record

    def set_evidence_ids(self, action: TypedAction, evidence_ids: list[str]) -> None:
        with self._lock:
            record = self._require(action)
            if any(not isinstance(item, str) or not item for item in evidence_ids):
                raise ContractValidationError("evidence ids must be non-empty strings")
            record.evidence_ids = list(dict.fromkeys(evidence_ids))
            self._persist(action.run_id)

    def abort(self, action: TypedAction) -> None:
        with self._lock:
            record = self._require(action)
            if record.state in {ReservationState.COMMITTED, ReservationState.APPLIED, ReservationState.IN_DOUBT}:
                raise ReservationConflict(f"cannot abort {record.state}")
            record.state = ReservationState.ABORTED
            self._persist(action.run_id)

    def mark_in_doubt(self, action: TypedAction) -> None:
        with self._lock:
            record = self._require(action)
            if record.state not in {ReservationState.PREPARED, ReservationState.APPLIED}:
                raise ReservationConflict(f"cannot mark {record.state} as IN_DOUBT")
            record.state = ReservationState.IN_DOUBT
            self._persist(action.run_id)

    def recover(self, action: TypedAction, *, observe: Callable[[], Mapping[str, Any]]) -> str:
        """Re-observe before deciding whether an interrupted apply may be committed."""
        with self._lock:
            record = self._require(action)
            if record.state not in {ReservationState.IN_DOUBT, ReservationState.APPLIED}:
                return record.state
        observed = dict(observe())
        if observed.get("revision") == action.expected_revision and observed.get("value") != action.value:
            with self._lock:
                self._records[record.key].state = ReservationState.ABORTED
                self._persist(action.run_id)
            return ReservationState.ABORTED
        if observed.get("value") == action.value:
            with self._lock:
                self._records[record.key].state = ReservationState.COMMITTED
                self._persist(action.run_id)
            return ReservationState.COMMITTED
        return ReservationState.IN_DOUBT

    def _require(self, action: TypedAction) -> ReservationRecord:
        record = self.get(action)
        if record is None:
            raise ReservationConflict("action has no reservation")
        return record


@dataclass
class IdempotencyRecord:
    key: str
    action_digest: str
    state: str
    provider_result: dict[str, Any] | None = None
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "action_digest": self.action_digest, "state": self.state, "provider_result": self.provider_result, "evidence_ids": list(self.evidence_ids)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IdempotencyRecord":
        evidence_ids = value.get("evidence_ids", [])
        if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
            raise ContractValidationError("idempotency evidence_ids are invalid")
        return cls(
            key=str(value["key"]),
            action_digest=str(value["action_digest"]),
            state=str(value["state"]),
            provider_result=dict(value["provider_result"]) if isinstance(value.get("provider_result"), Mapping) else None,
            evidence_ids=list(evidence_ids),
        )


class IdempotencyLedger:
    def __init__(self, persistence: ReferenceGateStore | None = None) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.RLock()
        self.persistence = persistence
        self._loaded_runs: set[str] = set()

    def _ensure_loaded(self, run_id: str) -> None:
        if self.persistence is None or run_id in self._loaded_runs:
            return
        data = self.persistence.load_idempotency(run_id)
        self._records.update({key: IdempotencyRecord.from_dict(item) for key, item in (data.get("records") or {}).items()})
        self._loaded_runs.add(run_id)

    def _persist(self, run_id: str) -> None:
        if self.persistence is not None:
            self.persistence.save_idempotency(run_id, {key: record.to_dict() for key, record in self._records.items()})

    def begin(self, action: TypedAction) -> IdempotencyRecord | None:
        with self._lock:
            self._ensure_loaded(action.run_id)
            current = self._records.get(action.idempotency_key)
            if current is not None:
                if current.action_digest != action.action_digest:
                    raise ContractValidationError("idempotency key was reused with a different action digest")
                if current.state == ReservationState.COMMITTED:
                    return current
                raise ReservationConflict("idempotency key is already in flight")
            self._records[action.idempotency_key] = IdempotencyRecord(action.idempotency_key, action.action_digest, ReservationState.PREPARED)
            self._persist(action.run_id)
            return None

    def commit(self, action: TypedAction, result: ProviderResult) -> None:
        with self._lock:
            record = self._records.get(action.idempotency_key)
            if record is None or record.action_digest != action.action_digest:
                raise ContractValidationError("idempotency record is missing or mismatched")
            record.state = ReservationState.COMMITTED
            record.provider_result = result.to_dict()
            self._persist(action.run_id)

    def set_evidence_ids(self, action: TypedAction, evidence_ids: list[str]) -> None:
        with self._lock:
            self._ensure_loaded(action.run_id)
            record = self._records.get(action.idempotency_key)
            if record is None or record.action_digest != action.action_digest:
                raise ContractValidationError("idempotency record is missing or mismatched")
            if any(not isinstance(item, str) or not item for item in evidence_ids):
                raise ContractValidationError("evidence ids must be non-empty strings")
            record.evidence_ids = list(dict.fromkeys(evidence_ids))
            self._persist(action.run_id)

    def mark_in_doubt(self, action: TypedAction) -> None:
        with self._lock:
            self._ensure_loaded(action.run_id)
            record = self._records.get(action.idempotency_key)
            if record is None or record.action_digest != action.action_digest:
                raise ContractValidationError("idempotency record is missing or mismatched")
            if record.state == ReservationState.PREPARED:
                record.state = ReservationState.IN_DOUBT
                self._persist(action.run_id)

    def abort(self, action: TypedAction) -> None:
        with self._lock:
            record = self._records.get(action.idempotency_key)
            if record is not None:
                record.state = ReservationState.ABORTED
                self._persist(action.run_id)


class ProviderPostConditionVerifier:
    def verify(self, *, action: TypedAction, result: ProviderResult, before_revision: str | None = None) -> None:
        if result.status != "passed" or result.provider_ref != "unity_artist_cli":
            raise ContractValidationError("ProviderResult did not pass through the canonical UnityArtist provider")
        if result.action_id != action.action_id or result.project != action.project:
            raise ContractValidationError("ProviderResult action/project binding mismatch")
        if result.target != action.target or result.property_path != action.property_path:
            raise ContractValidationError("ProviderResult target/property binding mismatch")
        if result.mutation_count != 1 or result.boundary_violations:
            raise ContractValidationError("ProviderResult reports an invalid mutation or boundary violation")
        if result.after_value != action.value:
            raise ContractValidationError("ProviderResult after_value does not satisfy TypedAction")
        if before_revision is not None and not before_revision:
            raise ContractValidationError("before revision was not observed")
        exact = result.exact_diff
        if exact.get("target") != action.target["guid"] or exact.get("property") != action.property_path:
            raise ContractValidationError(
                "ProviderResult exact diff is outside scope: "
                f"target={exact.get('target')!r}, property={exact.get('property')!r}, "
                f"expected_target={action.target['guid']!r}, expected_property={action.property_path!r}"
            )
        if float(exact.get("after")) != action.value or float(exact.get("before")) != result.before_value:
            raise ContractValidationError("ProviderResult exact diff does not match observed values")
        if not result.observed_revision:
            raise ContractValidationError("ProviderResult final revision was not observed")


class RuntimeDispatchGate:
    """Dispatches only after revalidation and commits only after durable evidence."""

    def __init__(self, *, validator: CrossContractValidator | None = None, reservations: ActionReservationStore | None = None, idempotency: IdempotencyLedger | None = None, postconditions: ProviderPostConditionVerifier | None = None, approval_resolver: Any | None = None, persistence_root: Any | None = None) -> None:
        self.approval_resolver = approval_resolver
        persistence = ReferenceGateStore(persistence_root) if persistence_root is not None else None
        self.validator = validator or CrossContractValidator(approval_resolver)
        self.reservations = reservations or ActionReservationStore(persistence)
        self.idempotency = idempotency or IdempotencyLedger(persistence)
        self.postconditions = postconditions or ProviderPostConditionVerifier()

    def dispatch(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        grant: SurfaceGrant,
        action: TypedAction,
        dispatch_provider: Callable[[TypedAction], ProviderResult | Mapping[str, Any]],
        evidence_writer: Callable[[TypedAction, ProviderResult], list[str]] | None = None,
    ) -> dict[str, Any]:
        self.validator.validate(task=task, approval=approval, grant=grant, action=action, approval_resolver=self.approval_resolver)
        prior = self.idempotency.begin(action)
        if prior is not None:
            if prior.provider_result is None:
                raise ReservationConflict("committed idempotency record has no ProviderResult")
            return {"status": "idempotent", "provider_result": ProviderResult.from_dict(prior.provider_result), "evidence_ids": list(prior.evidence_ids)}
        try:
            reservation = self.reservations.reserve(action)
            if reservation.state == ReservationState.COMMITTED and reservation.provider_result is not None:
                result = ProviderResult.from_dict(reservation.provider_result)
                self.idempotency.commit(action, result)
                return {"status": "idempotent", "provider_result": result, "evidence_ids": list(reservation.evidence_ids)}
            raw = dispatch_provider(action)
            result = raw if isinstance(raw, ProviderResult) else ProviderResult.from_dict(raw)
            self.postconditions.verify(action=action, result=result, before_revision=action.expected_revision)
            self.reservations.mark_applied(action, result)
            evidence_ids = evidence_writer(action, result) if evidence_writer is not None else []
            self.reservations.set_evidence_ids(action, list(evidence_ids))
            self.idempotency.set_evidence_ids(action, list(evidence_ids))
            self.reservations.commit(action)
            self.idempotency.commit(action, result)
            return {"status": "applied", "provider_result": result, "evidence_ids": list(evidence_ids)}
        except Exception:
            try:
                current = self.reservations.get(action)
                if current is not None and current.state in {ReservationState.PREPARED, ReservationState.APPLIED}:
                    self.reservations.mark_in_doubt(action)
                self.idempotency.mark_in_doubt(action)
            finally:
                pass
            raise

    def recover(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        grant: SurfaceGrant,
        action: TypedAction,
        evidence_writer: Callable[[TypedAction, ProviderResult], list[str]],
        observe: Callable[[ProviderResult], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Replay durable evidence for an IN_DOUBT action without reapplying it."""
        self.validator.validate(task=task, approval=approval, grant=grant, action=action, approval_resolver=self.approval_resolver)
        reservation = self.reservations.get(action)
        if reservation is None or reservation.state != ReservationState.IN_DOUBT or reservation.provider_result is None:
            raise ReservationConflict("action is not awaiting crash recovery")
        result = ProviderResult.from_dict(reservation.provider_result)
        observed = dict(observe(result) if observe is not None else {"value": result.after_value, "revision": result.observed_revision})
        if observed.get("value") != result.after_value or not observed.get("revision"):
            raise ContractValidationError("recovery observation does not match persisted ProviderResult")
        evidence_ids = evidence_writer(action, result)
        self.reservations.set_evidence_ids(action, list(evidence_ids))
        self.idempotency.set_evidence_ids(action, list(evidence_ids))
        self.reservations.commit(action)
        self.idempotency.commit(action, result)
        return {"status": "recovered", "provider_result": result, "evidence_ids": list(evidence_ids)}


def reference_definition_fingerprint() -> dict[str, str]:
    return {
        "schema_version": "1.0", "architecture_version": "reference-v1.1", "policy_revision": "reference-v1.1",
        "prompt_revision": "reference-v1.1", "context_revision": "reference-v1.1", "graph_revision": "reference-v1.1",
        "runtime_profile_revision": "reference-v1.1", "tool_schema_revision": "reference-v1.1",
        "checkpoint_schema_revision": "reference-v1.1", "evidence_schema_revision": "reference-v1.1",
        "eval_contract_revision": "reference-v1.1",
    }


def append_reference_evidence(*, store: Any, task: TaskContract, action: Any, result: ProviderResult, evidence: EvidenceRecord, evidence_type: str) -> dict[str, Any]:
    """Write a v1.1 reference record through the existing durable EvidenceStore."""
    if evidence.evidence_type != evidence_type or evidence.task_id != task.task_id or evidence.action_id != action.action_id:
        raise ContractValidationError("reference evidence binding mismatch")
    record = {
        "schema_version": "1.1", "evidence_id": evidence.evidence_id, "run_id": task.run_id,
        "step_id": action.action_id, "source_type": "unity_artist_reference", "source_ref": evidence_type,
        "timestamp": datetime.now(timezone.utc).isoformat(), "hash": sha256_jcs(evidence.to_dict()),
        "payload_ref": f"reference://{evidence.evidence_id}",
        "producer": "UnityAgent.ReferenceImplementation.v1.1", "status": "passed", "provenance": ["runtime", "unity_artist_cli", evidence_type],
        "definition_fingerprint": reference_definition_fingerprint(), "capability": "domain.workflow",
        "provider_ref": result.provider_ref, "project_root": task.project["root"],
        "environment": {"platform": "windows", "reference_fixture": False},
        "target": {"guid": action.target["guid"], "component_type": action.target["component_type"], "property": action.property_path},
        "safety_strength": 5, "evidence_strength": 5, "completion": "complete", "observation_state": "observed",
        "failure_class": None, "observed_evidence": [evidence_type], "required_evidence": [evidence_type],
        "raw_refs": [evidence.evidence_id], "mutation_provenance": {"action_id": action.action_id, "action_digest": action.action_digest, "evidence_digest": evidence.evidence_digest, "reference_payload": evidence.payload},
        "latency_ms": 0, "fallback_from": None, "durability": "current_run",
    }
    return append_runtime_execution_evidence(store, record)


class EvidenceCompletionGate:
    """Runtime-only final gate; absence or uncertainty is never success."""

    def __init__(self, evidence_store: Any, approval_resolver: Any | None = None) -> None:
        self.evidence_store = evidence_store
        self.approval_resolver = approval_resolver

    def evaluate(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        grant: SurfaceGrant,
        actions: list[TypedAction],
        provider_results: list[ProviderResult],
        reservations: ActionReservationStore,
        evidence_ids: list[str],
        final_revision: str | None,
        ledger: RuntimeBudgetLedger,
        human_review: str = "approved",
        boundary_violations: list[str] | None = None,
    ) -> CompletionProof:
        reasons: list[str] = []
        violations = list(boundary_violations or [])
        try:
            CrossContractValidator(self.approval_resolver).validate(task=task, approval=approval, grant=grant, action=actions[0], approval_resolver=self.approval_resolver)
        except (IndexError, ContractValidationError) as exc:
            reasons.append(str(exc))
        if approval.status != "active" or approval.human_review != "approved" or human_review != "approved":
            reasons.append("human approval is not active")
        if len(actions) != 1 or len(provider_results) != len(actions):
            reasons.append("final action/result cardinality is invalid")
        expected_evidence = set(task.required_evidence)
        found_evidence: set[str] = set()
        bound_action_id = actions[0].action_id if actions else None
        bound_action_digest = actions[0].action_digest if actions else None
        for evidence_id in evidence_ids:
            try:
                stored = self.evidence_store.get(evidence_id)
            except Exception:
                reasons.append(f"required evidence is not durable: {evidence_id}")
                continue
            provenance = stored.get("mutation_provenance") if isinstance(stored.get("mutation_provenance"), Mapping) else {}
            if stored.get("verification_status") != "passed" or stored.get("observation_state") != "observed" or stored.get("durability") != "durable":
                reasons.append(f"evidence is not durably observed: {evidence_id}")
                continue
            reference_type = stored.get("source_ref")
            if reference_type in ALLOWED_EVIDENCE and stored.get("run_id") == task.run_id and provenance.get("action_id") == bound_action_id and provenance.get("action_digest") == bound_action_digest:
                found_evidence.add(str(reference_type))
            else:
                reasons.append(f"evidence binding is outside the approved action: {evidence_id}")
        if not expected_evidence.issubset(found_evidence):
            reasons.append(f"required evidence floor is incomplete: {sorted(expected_evidence - found_evidence)}")
        committed: list[str] = []
        for action in actions:
            reservation = reservations.get(action)
            if reservation is None or reservation.state != ReservationState.COMMITTED:
                reasons.append(f"action {action.action_id} is not COMMITTED")
            else:
                committed.append(action.action_id)
        if not provider_results:
            reasons.append("final ProviderResult is missing")
        else:
            for result in provider_results:
                if result.status != "passed" or result.boundary_violations:
                    reasons.append("ProviderResult is not a clean passed observation")
                if final_revision is None or result.observed_revision != final_revision:
                    reasons.append("final revision is not bound to the observed ProviderResult")
        if violations:
            reasons.append("boundary violations were recorded")
        if not ledger.within_limits():
            reasons.append("runtime budget was exceeded")
        state = "eligible" if not reasons else "blocked"
        decision = CompletionDecision._issue(
            task_id=task.task_id, run_id=task.run_id, state=state, final_revision=final_revision if state == "eligible" else None,
            evidence_ids=list(evidence_ids), committed_action_ids=committed, budget=ledger.snapshot(),
            boundary_violations=violations, reason="eligible" if state == "eligible" else "; ".join(reasons),
        )
        return CompletionProof._issue(decision)


class CompletionCoordinator:
    """The only API that converts a Runtime CompletionDecision to success."""

    def present(self, proof: CompletionProof, *, ledger: RuntimeBudgetLedger) -> dict[str, Any]:
        if not isinstance(proof, CompletionProof):
            return {"status": "blocked", "completion": {"state": "blocked", "reason": "CompletionProof is required"}}
        try:
            ledger.consume("parent_total_calls", 1)
        except BudgetExceeded:
            return {"status": "blocked", "completion": {**proof.to_dict(), "state": "blocked", "reason": "parent completion call exceeded budget"}}
        try:
            consumed = proof.consume()
            decision = CompletionDecision.from_dict(consumed.to_dict())
        except (ContractValidationError, TypeError, ValueError) as exc:
            return {"status": "blocked", "completion": {"state": "blocked", "reason": str(exc)}}
        if decision.state != "eligible":
            return {"status": "blocked", "completion": decision.to_dict()}
        return {"status": "completed", "completion": decision.to_dict()}
