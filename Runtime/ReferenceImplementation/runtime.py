"""Deterministic Runtime gates for the canonical generic SubAgent path."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from contextlib import nullcontext
from pathlib import Path
import threading
import time
from typing import Any, Callable, Mapping

from Persistence.Evidence.evidence_store import EvidenceStore
from Persistence.Evidence.runtime_adapter import append_runtime_execution_evidence
from Persistence.Reference.reference_gate_store import ReferenceGateStore
from Persistence.Store.atomic_store import PersistenceError, safe_id

from .authority import ApprovalDecisionResolver, BudgetExceeded, RuntimeBudgetLedger, utc_now
from .canonicalization import digest_for, sha256_jcs
from .contracts import (
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
from .profiles import ProfileValidationError, SubAgentProfile, default_profile, profile_for_task_object
from Runtime.Tooling.Environment.project_identity import canonical_scene_path, same_project_root


def _validated_evidence_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ContractValidationError("durable evidence ids must be a non-empty list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ContractValidationError("evidence ids must be non-empty strings")
        try:
            safe_id(item, "evidence_id")
        except PersistenceError as exc:
            raise ContractValidationError(f"evidence id is unsafe: {item!r}") from exc
        if item in result:
            raise ContractValidationError("evidence ids must be unique")
        result.append(item)
    return result


def _causal_proof(action: TypedAction, result: ProviderResult, observed: Mapping[str, Any]) -> bool:
    """Require an observed mutation marker, not merely an equal end value."""
    proof = observed.get("mutation_causality") or observed.get("causal_proof")
    if not isinstance(proof, Mapping):
        return False
    expected = {
        "run_id": action.run_id,
        "action_id": action.action_id,
        "action_digest": action.action_digest,
        "provider_result_digest": result.provider_result_digest,
        "before_revision": action.expected_revision,
        "after_revision": result.observed_revision,
        "before_value": result.before_value,
        "after_value": result.after_value,
    }
    if any(proof.get(key) != value for key, value in expected.items()):
        return False
    if proof.get("changed") is not True:
        return False
    return observed.get("revision") == result.observed_revision and observed.get("value") == result.after_value


def validate_reference_environment_snapshot(
    snapshot: Mapping[str, Any],
    *,
    project_root: str | Path,
    scene_path: str,
) -> str:
    """Authorize a mutation only from a complete, measured environment snapshot."""
    from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot

    value = dict(snapshot)
    try:
        validate_environment_snapshot(value)
    except Exception as exc:
        raise ContractValidationError(f"environment snapshot schema is invalid: {exc}") from exc
    project = value.get("project") if isinstance(value.get("project"), Mapping) else {}
    filesystem = value.get("filesystem") if isinstance(value.get("filesystem"), Mapping) else {}
    git = value.get("git") if isinstance(value.get("git"), Mapping) else {}
    editor = value.get("unity_editor") if isinstance(value.get("unity_editor"), Mapping) else {}
    cli = value.get("unity_cli") if isinstance(value.get("unity_cli"), Mapping) else {}
    artist = value.get("unity_artist_cli") if isinstance(value.get("unity_artist_cli"), Mapping) else {}
    pipeline = value.get("pipeline") if isinstance(value.get("pipeline"), Mapping) else {}
    required_true = {
        "project.exists": project.get("exists"),
        "project.identity_status": project.get("identity_status") == "bound",
        "project.required_paths.assets": (project.get("required_paths") or {}).get("assets"),
        "project.required_paths.packages": (project.get("required_paths") or {}).get("packages"),
        "project.required_paths.project_settings": (project.get("required_paths") or {}).get("project_settings"),
        "filesystem.readable": filesystem.get("readable"),
        "filesystem.writable": filesystem.get("writable"),
        "filesystem.writable_in_mutation_scope": filesystem.get("writable_in_mutation_scope"),
        "git.available": git.get("available"),
        "git.repository_bound": git.get("repository_bound"),
        "unity_editor.installed": editor.get("installed"),
        "unity_editor.running": editor.get("running"),
        "unity_editor.project_bound": editor.get("project_bound"),
        "unity_editor.project_version_match": editor.get("project_version_match"),
        "unity_editor.safe_mode": editor.get("safe_mode") is False,
        "unity_editor.binding_status": editor.get("binding_status") == "bound",
        "unity_cli.available": cli.get("available"),
        "unity_artist_cli.available": artist.get("available"),
        "unity_artist_cli.project_bound": artist.get("project_bound"),
        "unity_artist_cli.package_installed": artist.get("package_installed"),
        "unity_artist_cli.pipeline_reachable": artist.get("pipeline_reachable"),
        "unity_artist_cli.binding_status": artist.get("binding_status") == "bound",
        "pipeline.installed": pipeline.get("installed"),
        "pipeline.reachable": pipeline.get("reachable"),
    }
    uncertain = sorted(name for name, observed in required_true.items() if observed is not True)
    if uncertain:
        raise ContractValidationError(f"environment snapshot is incomplete or unsafe: {uncertain}")
    requested_root = str(Path(project_root).expanduser().resolve(strict=False))
    snapshot_root = project.get("root")
    if not isinstance(snapshot_root, str) or not same_project_root(snapshot_root, requested_root):
        raise ContractValidationError("environment snapshot project root is not bound to the requested project")
    canonical_scene_path(requested_root, scene_path, require_exists=True)
    for name, section in (("unity_editor", editor), ("unity_cli", cli), ("unity_artist_cli", artist)):
        executable = section.get("executable_path")
        if not isinstance(executable, str) or not Path(executable).is_file():
            raise ContractValidationError(f"environment snapshot {name} executable was not observed on disk")
    if not isinstance(editor.get("bound_instance_id"), str) or not editor.get("bound_instance_id"):
        raise ContractValidationError("environment snapshot has no bound Unity Editor instance")
    if not isinstance(artist.get("bound_instance_id"), str) or not artist.get("bound_instance_id"):
        raise ContractValidationError("environment snapshot has no bound UnityArtist instance")
    non_empty_facts = {
        "project.unity_version": (project, "unity_version"),
        "unity_editor.version": (editor, "version"),
        "unity_cli.version": (cli, "version"),
        "unity_artist_cli.version": (artist, "version"),
        "unity_artist_cli.package_version": (artist, "package_version"),
        "unity_artist_cli.unity_version": (artist, "unity_version"),
        "unity_artist_cli.render_pipeline": (artist, "render_pipeline"),
        "unity_artist_cli.support_tier": (artist, "support_tier"),
        "unity_artist_cli.compatibility_backend": (artist, "compatibility_backend"),
    }
    missing_facts = sorted(
        name for name, (section, field_name) in non_empty_facts.items()
        if not isinstance(section.get(field_name), str) or not section.get(field_name).strip()
    )
    if missing_facts:
        raise ContractValidationError(f"environment snapshot did not measure required identity facts: {missing_facts}")
    if not isinstance(artist.get("capabilities"), list) or not artist.get("capabilities"):
        raise ContractValidationError("environment snapshot did not measure UnityArtist capabilities")
    if not isinstance(value.get("binding_fingerprint"), str) or not value.get("binding_fingerprint") or value.get("binding_fingerprint") == "0" * 64:
        raise ContractValidationError("environment snapshot binding fingerprint was not measured")
    if project.get("unity_version") and artist.get("unity_version") not in {None, project.get("unity_version")}:
        raise ContractValidationError("UnityArtist support proof is bound to a different Unity version")
    return canonical_scene_path(requested_root, scene_path, require_exists=True)


class CrossContractValidator:
    """Revalidates every cross-binding at the last trusted boundary."""

    def __init__(self, approval_resolver: Any | None = None, *, profile: SubAgentProfile | None = None) -> None:
        self.approval_resolver = approval_resolver
        self.profile = profile

    def validate(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        grant: SurfaceGrant,
        action: TypedAction,
        now: datetime | None = None,
        approval_resolver: Any | None = None,
        profile: SubAgentProfile | None = None,
    ) -> None:
        selected = profile or self.profile or profile_for_task_object(task)
        try:
            TaskContract.from_dict(task.to_dict(), profile=selected)
            ApprovalDecision.from_dict(approval.to_dict(), profile=selected)
            SurfaceGrant.from_dict(grant.to_dict(), profile=selected)
            TypedAction.from_dict(action.to_dict(), profile=selected)
        except ProfileValidationError as exc:
            raise ContractValidationError(f"SubAgent profile validation failed: {exc}") from exc
        if approval.task_id != task.task_id or approval.run_id != task.run_id:
            raise ContractValidationError("ApprovalDecision task/run binding mismatch")
        if approval.project != task.project or approval.project_fingerprint != task.project_fingerprint:
            raise ContractValidationError("ApprovalDecision project binding mismatch")
        if approval.contract_digest != task.contract_digest:
            raise ContractValidationError("ApprovalDecision contract digest mismatch")
        if approval.scope != task.scope:
            raise ContractValidationError("ApprovalDecision scope differs from TaskContract")
        if grant.audience != selected.audience or grant.task_id != task.task_id or grant.run_id != task.run_id:
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
        if action.target["guid"] != target_guid or action.target["component_type"] != selected.scope["component_type"]:
            raise ContractValidationError("TypedAction target is outside the approved scope")
        if action.property_path not in task.scope["property_paths"] or action.property_path != selected.action_property_path:
            raise ContractValidationError("TypedAction property is outside the approved scope")
        if action.mutation_channel not in task.scope["mutation_channels"]:
            raise ContractValidationError("TypedAction mutation channel is outside the approved scope")
        if action.capability not in grant.capabilities or action.capability != approval.capability:
            raise ContractValidationError("TypedAction capability is not granted")
        try:
            selected.validate_value(action.value)
        except ProfileValidationError as exc:
            raise ContractValidationError(f"TypedAction value is outside the approved profile: {exc}") from exc
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
    run_id: str
    key: str
    action_id: str
    action_digest: str
    state: str
    expected_revision: str
    provider_result: dict[str, Any] | None = None
    evidence_ids: list[str] = field(default_factory=list)
    causal_proof: dict[str, Any] | None = None
    recovery_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "key": self.key, "action_id": self.action_id, "action_digest": self.action_digest,
            "state": self.state, "expected_revision": self.expected_revision,
            "provider_result": self.provider_result, "evidence_ids": list(self.evidence_ids),
            "causal_proof": self.causal_proof, "recovery_reason": self.recovery_reason,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, expected_run_id: str | None = None) -> "ReservationRecord":
        required = {"run_id", "key", "action_id", "action_digest", "state", "expected_revision", "evidence_ids"}
        if not isinstance(value, Mapping) or not required.issubset(value):
            raise ContractValidationError("reservation record schema is incomplete")
        run_id = value.get("run_id")
        if not isinstance(run_id, str) or not run_id or (expected_run_id is not None and run_id != expected_run_id):
            raise ContractValidationError("reservation record run binding is invalid")
        key = value.get("key")
        if not isinstance(key, str) or not key.startswith(f"run={run_id}:"):
            raise ContractValidationError("reservation record key is outside its run namespace")
        state = value.get("state")
        if state not in {
            ReservationState.PREPARED, ReservationState.APPLIED, ReservationState.COMMITTED,
            ReservationState.ABORTED, ReservationState.IN_DOUBT,
        }:
            raise ContractValidationError("reservation state is invalid")
        evidence_ids = value.get("evidence_ids", [])
        if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
            raise ContractValidationError("reservation evidence_ids are invalid")
        return cls(
            run_id=run_id,
            key=key,
            action_id=str(value["action_id"]),
            action_digest=str(value["action_digest"]),
            state=state,
            expected_revision=str(value["expected_revision"]),
            provider_result=dict(value["provider_result"]) if isinstance(value.get("provider_result"), Mapping) else None,
            evidence_ids=list(evidence_ids),
            causal_proof=dict(value["causal_proof"]) if isinstance(value.get("causal_proof"), Mapping) else None,
            recovery_reason=str(value["recovery_reason"]) if value.get("recovery_reason") is not None else None,
        )


class ActionReservationStore:
    """Thread-safe reservation state machine with a full action namespace."""

    def __init__(self, persistence: ReferenceGateStore | None = None, *, run_id: str | None = None) -> None:
        self._records: dict[str, ReservationRecord] = {}
        self._lock = threading.RLock()
        self.persistence = persistence
        self.run_id = run_id
        self._loaded_runs: set[str] = set()

    @staticmethod
    def _key(action: TypedAction) -> str:
        return (
            f"run={action.run_id}:project={action.project_fingerprint}:"
            f"action={action.action_digest}:idempotency={action.idempotency_key}:"
            f"target={action.target['guid']}:property={action.property_path}"
        )

    def _ensure_loaded(self, run_id: str) -> None:
        if self.persistence is None:
            return
        data = self.persistence.load_reservations(run_id)
        loaded: dict[str, ReservationRecord] = {}
        for key, item in (data.get("records") or {}).items():
            record = ReservationRecord.from_dict(item, expected_run_id=run_id)
            if key != record.key:
                raise ContractValidationError("reservation persistence key does not match record key")
            loaded[key] = record
        self._records = {
            key: record for key, record in self._records.items() if record.run_id != run_id
        }
        self._records.update(loaded)
        self._loaded_runs.add(run_id)

    def _run_lock(self, run_id: str):
        return self.persistence.locked(run_id) if self.persistence is not None else nullcontext()

    def _persist(self, run_id: str) -> None:
        if self.persistence is not None:
            records = {
                key: record.to_dict()
                for key, record in self._records.items()
                if record.run_id == run_id
            }
            self.persistence.save_reservations(run_id, records)

    def _assert_run(self, action: TypedAction) -> None:
        if self.run_id is not None and action.run_id != self.run_id:
            raise ContractValidationError("action run_id does not match reservation store")
        try:
            safe_id(action.run_id, "run_id")
        except PersistenceError as exc:
            raise ContractValidationError("action run_id is not a safe Persistence identifier") from exc

    def reserve(self, action: TypedAction) -> ReservationRecord:
        self._assert_run(action)
        key = self._key(action)
        with self._lock, self._run_lock(action.run_id):
            self._ensure_loaded(action.run_id)
            current = self._records.get(key)
            if current is not None:
                if current.action_digest != action.action_digest:
                    raise ReservationConflict("reservation key is bound to a different action digest")
                if current.state == ReservationState.COMMITTED:
                    return current
                raise ReservationConflict(f"reservation is already {current.state}")
            record = ReservationRecord(action.run_id, key, action.action_id, action.action_digest, ReservationState.PREPARED, action.expected_revision)
            self._records[key] = record
            self._persist(action.run_id)
            return record

    def get(self, action: TypedAction) -> ReservationRecord | None:
        self._assert_run(action)
        key = self._key(action)
        with self._lock, self._run_lock(action.run_id):
            self._ensure_loaded(action.run_id)
            return self._records.get(key)

    def mark_applied(self, action: TypedAction, result: ProviderResult) -> None:
        self._assert_run(action)
        with self._lock, self._run_lock(action.run_id):
            record = self._require(action)
            if record.state != ReservationState.PREPARED:
                raise ReservationConflict(f"cannot mark {record.state} as APPLIED")
            if result.action_id != action.action_id or result.observed_revision == action.expected_revision:
                raise ContractValidationError("ProviderResult does not prove a new revision for this action")
            record.provider_result = result.to_dict()
            record.causal_proof = {
                "run_id": action.run_id,
                "action_id": action.action_id,
                "action_digest": action.action_digest,
                "provider_result_digest": result.provider_result_digest,
                "before_revision": action.expected_revision,
                "after_revision": result.observed_revision,
                "before_value": result.before_value,
                "after_value": result.after_value,
                "changed": True,
            }
            record.state = ReservationState.APPLIED
            self._persist(action.run_id)

    def commit(self, action: TypedAction) -> ReservationRecord:
        self._assert_run(action)
        with self._lock, self._run_lock(action.run_id):
            record = self._require(action)
            if record.state == ReservationState.COMMITTED:
                if record.provider_result is None or not record.evidence_ids:
                    raise ReservationConflict("COMMITTED reservation has no durable evidence binding")
                return record
            if record.state not in {ReservationState.APPLIED, ReservationState.IN_DOUBT}:
                raise ReservationConflict(f"cannot commit {record.state}")
            if record.provider_result is None or not record.evidence_ids:
                raise ReservationConflict("cannot COMMIT before ProviderResult and durable evidence are bound")
            record.state = ReservationState.COMMITTED
            self._persist(action.run_id)
            return record

    def set_evidence_ids(self, action: TypedAction, evidence_ids: list[str]) -> None:
        self._assert_run(action)
        with self._lock, self._run_lock(action.run_id):
            record = self._require(action)
            record.evidence_ids = _validated_evidence_ids(evidence_ids)
            self._persist(action.run_id)

    def abort(self, action: TypedAction) -> None:
        self._assert_run(action)
        with self._lock, self._run_lock(action.run_id):
            record = self._require(action)
            if record.state in {ReservationState.COMMITTED, ReservationState.APPLIED, ReservationState.IN_DOUBT}:
                raise ReservationConflict(f"cannot abort {record.state}")
            record.state = ReservationState.ABORTED
            self._persist(action.run_id)

    def mark_in_doubt(self, action: TypedAction) -> None:
        self._assert_run(action)
        with self._lock, self._run_lock(action.run_id):
            record = self._require(action)
            if record.state not in {ReservationState.PREPARED, ReservationState.APPLIED}:
                raise ReservationConflict(f"cannot mark {record.state} as IN_DOUBT")
            record.state = ReservationState.IN_DOUBT
            self._persist(action.run_id)

    def recover(self, action: TypedAction, *, observe: Callable[[], Mapping[str, Any]]) -> str:
        """Re-observe before deciding whether an interrupted apply may be committed."""
        self._assert_run(action)
        with self._lock, self._run_lock(action.run_id):
            record = self._require(action)
            if record.state not in {ReservationState.IN_DOUBT, ReservationState.APPLIED}:
                return record.state
            provider_data = record.provider_result
            record_key = record.key
        if provider_data is None:
            return ReservationState.IN_DOUBT
        result = ProviderResult.from_dict(provider_data)
        observed = dict(observe())
        if observed.get("revision") == action.expected_revision and observed.get("value") != action.value:
            with self._lock, self._run_lock(action.run_id):
                self._ensure_loaded(action.run_id)
                current = self._records.get(record_key)
                if current is None:
                    raise ReservationConflict("action reservation disappeared during recovery")
                if current.state != ReservationState.IN_DOUBT:
                    return current.state
                current.state = ReservationState.ABORTED
                current.recovery_reason = "target remained at the pre-action revision"
                self._persist(action.run_id)
            return ReservationState.ABORTED
        if _causal_proof(action, result, observed):
            with self._lock, self._run_lock(action.run_id):
                self._ensure_loaded(action.run_id)
                current = self._records.get(record_key)
                if current is None:
                    raise ReservationConflict("action reservation disappeared during recovery")
                if current.state == ReservationState.COMMITTED:
                    return current.state
                if current.state not in {ReservationState.IN_DOUBT, ReservationState.APPLIED}:
                    return current.state
                # Recovery only proves the mutation happened.  Evidence remains
                # a separate durable prerequisite for COMMITTED.
                current.causal_proof = {
                    **dict(observed.get("mutation_causality") or observed.get("causal_proof")),
                    "before_value": result.before_value,
                    "after_value": result.after_value,
                }
                self._persist(action.run_id)
            return ReservationState.APPLIED
        if observed.get("value") == action.value:
            with self._lock, self._run_lock(action.run_id):
                self._ensure_loaded(action.run_id)
                current = self._records.get(record_key)
                if current is None:
                    raise ReservationConflict("action reservation disappeared during recovery")
                if current.state != ReservationState.IN_DOUBT:
                    return current.state
                current.state = ReservationState.ABORTED
                current.recovery_reason = "equal value lacks this-run mutation causality proof"
                self._persist(action.run_id)
            return ReservationState.ABORTED
        return ReservationState.IN_DOUBT

    def _require(self, action: TypedAction) -> ReservationRecord:
        self._ensure_loaded(action.run_id)
        record = self._records.get(self._key(action))
        if record is None:
            raise ReservationConflict("action has no reservation")
        return record


@dataclass
class IdempotencyRecord:
    run_id: str
    key: str
    action_digest: str
    state: str
    provider_result: dict[str, Any] | None = None
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "key": self.key, "action_digest": self.action_digest, "state": self.state, "provider_result": self.provider_result, "evidence_ids": list(self.evidence_ids)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, expected_run_id: str | None = None) -> "IdempotencyRecord":
        required = {"run_id", "key", "action_digest", "state", "evidence_ids"}
        if not isinstance(value, Mapping) or not required.issubset(value):
            raise ContractValidationError("idempotency record schema is incomplete")
        run_id = value.get("run_id")
        if not isinstance(run_id, str) or not run_id or (expected_run_id is not None and run_id != expected_run_id):
            raise ContractValidationError("idempotency record run binding is invalid")
        key = value.get("key")
        if not isinstance(key, str) or not key.startswith(f"run={run_id}:"):
            raise ContractValidationError("idempotency record key is outside its run namespace")
        state = value.get("state")
        if state not in {
            ReservationState.PREPARED, ReservationState.IN_DOUBT,
            ReservationState.COMMITTED, ReservationState.ABORTED,
        }:
            raise ContractValidationError("idempotency state is invalid")
        evidence_ids = value.get("evidence_ids", [])
        if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
            raise ContractValidationError("idempotency evidence_ids are invalid")
        return cls(
            run_id=run_id,
            key=key,
            action_digest=str(value["action_digest"]),
            state=state,
            provider_result=dict(value["provider_result"]) if isinstance(value.get("provider_result"), Mapping) else None,
            evidence_ids=list(evidence_ids),
        )


class IdempotencyLedger:
    def __init__(self, persistence: ReferenceGateStore | None = None) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.RLock()
        self.persistence = persistence
        self._loaded_runs: set[str] = set()

    @staticmethod
    def _namespace(action: TypedAction) -> str:
        """Return the non-reusable namespace required by the Runtime protocol."""
        return (
            f"run={action.run_id}:project={action.project_fingerprint}:"
            f"action={action.action_digest}:idempotency={action.idempotency_key}"
        )

    @staticmethod
    def _claim(action: TypedAction) -> str:
        return f"run={action.run_id}:project={action.project_fingerprint}:idempotency={action.idempotency_key}"

    def _ensure_loaded(self, run_id: str) -> None:
        if self.persistence is None:
            return
        data = self.persistence.load_idempotency(run_id)
        loaded: dict[str, IdempotencyRecord] = {}
        for key, item in (data.get("records") or {}).items():
            record = IdempotencyRecord.from_dict(item, expected_run_id=run_id)
            if key != record.key:
                raise ContractValidationError("idempotency persistence key does not match record key")
            loaded[key] = record
        self._records = {
            key: record for key, record in self._records.items() if record.run_id != run_id
        }
        self._records.update(loaded)
        self._loaded_runs.add(run_id)

    def _run_lock(self, run_id: str):
        return self.persistence.locked(run_id) if self.persistence is not None else nullcontext()

    def _persist(self, run_id: str) -> None:
        if self.persistence is not None:
            records = {
                key: record.to_dict()
                for key, record in self._records.items()
                if record.run_id == run_id
            }
            self.persistence.save_idempotency(run_id, records)

    def begin(self, action: TypedAction) -> IdempotencyRecord | None:
        try:
            safe_id(action.run_id, "run_id")
        except PersistenceError as exc:
            raise ContractValidationError("action run_id is not a safe Persistence identifier") from exc
        with self._lock, self._run_lock(action.run_id):
            self._ensure_loaded(action.run_id)
            namespace = self._namespace(action)
            for record in self._records.values():
                if record.key == namespace:
                    continue
                if record.key.endswith(f":idempotency={action.idempotency_key}") and record.key.startswith(
                    f"run={action.run_id}:project={action.project_fingerprint}:"
                ) and record.action_digest != action.action_digest:
                    raise ContractValidationError("idempotency key was reused with a different action digest")
            current = self._records.get(namespace)
            if current is not None:
                if current.action_digest != action.action_digest:
                    raise ContractValidationError("idempotency key was reused with a different action digest")
                if current.state == ReservationState.COMMITTED:
                    return current
                raise ReservationConflict("idempotency key is already in flight")
            self._records[namespace] = IdempotencyRecord(action.run_id, namespace, action.action_digest, ReservationState.PREPARED)
            self._persist(action.run_id)
            return None

    def commit(self, action: TypedAction, result: ProviderResult) -> None:
        with self._lock, self._run_lock(action.run_id):
            self._ensure_loaded(action.run_id)
            record = self._records.get(self._namespace(action))
            if record is None or record.action_digest != action.action_digest:
                raise ContractValidationError("idempotency record is missing or mismatched")
            if not record.evidence_ids:
                raise ContractValidationError("cannot COMMIT idempotency before durable evidence is bound")
            if record.state not in {ReservationState.PREPARED, ReservationState.IN_DOUBT, ReservationState.COMMITTED}:
                raise ReservationConflict(f"cannot commit idempotency record in state {record.state}")
            record.state = ReservationState.COMMITTED
            record.provider_result = result.to_dict()
            self._persist(action.run_id)

    def set_evidence_ids(self, action: TypedAction, evidence_ids: list[str]) -> None:
        with self._lock, self._run_lock(action.run_id):
            self._ensure_loaded(action.run_id)
            record = self._records.get(self._namespace(action))
            if record is None or record.action_digest != action.action_digest:
                raise ContractValidationError("idempotency record is missing or mismatched")
            record.evidence_ids = _validated_evidence_ids(evidence_ids)
            self._persist(action.run_id)

    def mark_in_doubt(self, action: TypedAction) -> None:
        with self._lock, self._run_lock(action.run_id):
            self._ensure_loaded(action.run_id)
            record = self._records.get(self._namespace(action))
            if record is None or record.action_digest != action.action_digest:
                raise ContractValidationError("idempotency record is missing or mismatched")
            if record.state == ReservationState.PREPARED:
                record.state = ReservationState.IN_DOUBT
                self._persist(action.run_id)

    def abort(self, action: TypedAction) -> None:
        with self._lock, self._run_lock(action.run_id):
            self._ensure_loaded(action.run_id)
            record = self._records.get(self._namespace(action))
            if record is not None:
                record.state = ReservationState.ABORTED
                self._persist(action.run_id)


class ProviderPostConditionVerifier:
    def __init__(self, profile: SubAgentProfile | None = None) -> None:
        self.profile = profile or default_profile()

    def verify(self, *, action: TypedAction, result: ProviderResult, before_revision: str | None = None) -> None:
        profile = self.profile
        if result.status != "passed" or result.provider_ref != profile.provider_id:
            raise ContractValidationError("ProviderResult did not pass through the selected SubAgent provider")
        if result.action_id != action.action_id or result.project != action.project:
            raise ContractValidationError("ProviderResult action/project binding mismatch")
        if result.target != action.target or result.property_path != action.property_path:
            raise ContractValidationError("ProviderResult target/property binding mismatch")
        if result.target.get("component_type") != profile.scope["component_type"] or result.property_path != profile.action_property_path:
            raise ContractValidationError("ProviderResult target/property is outside the selected SubAgent profile")
        if result.mutation_count != 1 or result.boundary_violations or result.failure_class is not None:
            raise ContractValidationError("ProviderResult reports an invalid mutation or boundary violation")
        if result.after_value != action.value:
            raise ContractValidationError("ProviderResult after_value does not satisfy TypedAction")
        if before_revision is not None and not before_revision:
            raise ContractValidationError("before revision was not observed")
        exact = result.exact_diff
        if set(exact) != {"target", "property", "before", "after"}:
            raise ContractValidationError("ProviderResult exact diff is incomplete")
        if exact.get("target") != action.target["guid"] or exact.get("property") != action.property_path:
            raise ContractValidationError(
                "ProviderResult exact diff is outside scope: "
                f"target={exact.get('target')!r}, property={exact.get('property')!r}, "
                f"expected_target={action.target['guid']!r}, expected_property={action.property_path!r}"
            )
        try:
            exact_after = float(exact.get("after"))
            exact_before = float(exact.get("before"))
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("ProviderResult exact diff values were not observed as numbers") from exc
        if exact_after != action.value or exact_before != result.before_value:
            raise ContractValidationError("ProviderResult exact diff does not match observed values")
        if not result.observed_revision:
            raise ContractValidationError("ProviderResult final revision was not observed")
        if before_revision is not None and result.observed_revision == before_revision:
            raise ContractValidationError("ProviderResult does not prove that the mutation advanced the revision")
        if not set(profile.required_evidence).issubset(set(result.evidence)):
            raise ContractValidationError("ProviderResult evidence floor is incomplete")


class RuntimeDispatchGate:
    """Dispatches only after revalidation and commits only after durable evidence."""

    def __init__(
        self,
        *,
        validator: CrossContractValidator | None = None,
        reservations: ActionReservationStore | None = None,
        idempotency: IdempotencyLedger | None = None,
        postconditions: ProviderPostConditionVerifier | None = None,
        approval_resolver: Any | None = None,
        persistence_root: Any | None = None,
        evidence_store: EvidenceStore | None = None,
        profile: SubAgentProfile | None = None,
    ) -> None:
        self.approval_resolver = approval_resolver
        self.profile = profile
        persistence = ReferenceGateStore(persistence_root) if persistence_root is not None else None
        self.evidence_store = evidence_store or (EvidenceStore(persistence_root) if persistence_root is not None else None)
        self.validator = validator or CrossContractValidator(approval_resolver, profile=profile)
        self.reservations = reservations or ActionReservationStore(persistence)
        self.idempotency = idempotency or IdempotencyLedger(persistence)
        self.postconditions = postconditions or ProviderPostConditionVerifier(profile=profile)

    def _verify_durable_evidence(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        grant: SurfaceGrant,
        action: TypedAction,
        result: ProviderResult,
        evidence_ids: Any,
        scene_path: str | None = None,
        environment_snapshot: Mapping[str, Any] | None = None,
    ) -> list[str]:
        ids = _validated_evidence_ids(evidence_ids)
        if self.evidence_store is None:
            raise ContractValidationError("canonical EvidenceStore is required before COMMITTED")
        EvidenceCompletionGate(
            self.evidence_store,
            self.approval_resolver,
            profile=self.profile,
        ).validate_durable_evidence(
            task=task,
            approval=approval,
            grant=grant,
            action=action,
            result=result,
            evidence_ids=ids,
            scene_path=scene_path,
            environment_snapshot=environment_snapshot,
        )
        return ids

    def dispatch(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        grant: SurfaceGrant,
        action: TypedAction,
        dispatch_provider: Callable[[TypedAction], ProviderResult | Mapping[str, Any]],
        evidence_writer: Callable[[TypedAction, ProviderResult], list[str]] | None = None,
        ledger: RuntimeBudgetLedger | None = None,
        scene_path: str | None = None,
        environment_snapshot: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.validator.validate(task=task, approval=approval, grant=grant, action=action, approval_resolver=self.approval_resolver, profile=self.profile)
        if evidence_writer is None:
            raise ContractValidationError("mutating dispatch requires a durable evidence writer")
        if self.evidence_store is None:
            raise ContractValidationError("mutating dispatch requires the canonical EvidenceStore")
        prior = self.idempotency.begin(action)
        if prior is not None:
            if prior.provider_result is None:
                raise ReservationConflict("committed idempotency record has no ProviderResult")
            result = ProviderResult.from_dict(prior.provider_result)
            self.postconditions.verify(action=action, result=result, before_revision=action.expected_revision)
            evidence_ids = self._verify_durable_evidence(
                task=task, approval=approval, grant=grant, action=action,
                result=result, evidence_ids=prior.evidence_ids, scene_path=scene_path,
                environment_snapshot=environment_snapshot,
            )
            return {"status": "idempotent", "provider_result": result, "evidence_ids": evidence_ids}
        try:
            reservation = self.reservations.reserve(action)
            if reservation.state == ReservationState.COMMITTED and reservation.provider_result is not None:
                result = ProviderResult.from_dict(reservation.provider_result)
                self.postconditions.verify(action=action, result=result, before_revision=action.expected_revision)
                evidence_ids = self._verify_durable_evidence(
                    task=task, approval=approval, grant=grant, action=action,
                    result=result, evidence_ids=reservation.evidence_ids, scene_path=scene_path,
                    environment_snapshot=environment_snapshot,
                )
                self.idempotency.set_evidence_ids(action, evidence_ids)
                self.idempotency.commit(action, result)
                return {"status": "idempotent", "provider_result": result, "evidence_ids": evidence_ids}
            started = time.perf_counter()
            try:
                raw = dispatch_provider(action)
            finally:
                if ledger is not None:
                    ledger.record_child_observation(elapsed_ms=(time.perf_counter() - started) * 1000)
            result = ProviderResult.from_dict(raw.to_dict()) if isinstance(raw, ProviderResult) else ProviderResult.from_dict(raw)
            self.postconditions.verify(action=action, result=result, before_revision=action.expected_revision)
            self.reservations.mark_applied(action, result)
            evidence_ids = self._verify_durable_evidence(
                task=task,
                approval=approval,
                grant=grant,
                action=action,
                result=result,
                evidence_ids=evidence_writer(action, result),
                scene_path=scene_path,
                environment_snapshot=environment_snapshot,
            )
            self.reservations.set_evidence_ids(action, evidence_ids)
            self.idempotency.set_evidence_ids(action, evidence_ids)
            self.reservations.commit(action)
            self.idempotency.commit(action, result)
            return {"status": "applied", "provider_result": result, "evidence_ids": evidence_ids}
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
        scene_path: str | None = None,
        environment_snapshot: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Replay durable evidence for an IN_DOUBT action without reapplying it."""
        self.validator.validate(task=task, approval=approval, grant=grant, action=action, approval_resolver=self.approval_resolver, profile=self.profile)
        if evidence_writer is None or self.evidence_store is None:
            raise ContractValidationError("recovery requires the canonical durable EvidenceStore and writer")
        reservation = self.reservations.get(action)
        if reservation is None or reservation.state != ReservationState.IN_DOUBT or reservation.provider_result is None:
            raise ReservationConflict("action is not awaiting crash recovery")
        result = ProviderResult.from_dict(reservation.provider_result)
        self.postconditions.verify(action=action, result=result, before_revision=action.expected_revision)
        status = self.reservations.recover(
            action,
            observe=(lambda: dict(observe(result))) if observe is not None else (lambda: {}),
        )
        if status != ReservationState.APPLIED:
            raise ReservationConflict(f"recovery did not prove this run caused the mutation: {status}")
        evidence_ids = self._verify_durable_evidence(
            task=task,
            approval=approval,
            grant=grant,
            action=action,
            result=result,
            evidence_ids=evidence_writer(action, result),
            scene_path=scene_path,
            environment_snapshot=environment_snapshot,
        )
        self.reservations.set_evidence_ids(action, evidence_ids)
        self.idempotency.set_evidence_ids(action, evidence_ids)
        self.reservations.commit(action)
        self.idempotency.commit(action, result)
        return {"status": "recovered", "provider_result": result, "evidence_ids": evidence_ids}


def reference_definition_fingerprint() -> dict[str, str]:
    return {
        "schema_version": "1.0", "architecture_version": "reference-v1.1", "policy_revision": "reference-v1.1",
        "prompt_revision": "reference-v1.1", "context_revision": "reference-v1.1", "graph_revision": "reference-v1.1",
        "runtime_profile_revision": "reference-v1.1", "tool_schema_revision": "reference-v1.1",
        "checkpoint_schema_revision": "reference-v1.1", "evidence_schema_revision": "reference-v1.1",
        "eval_contract_revision": "reference-v1.1",
    }


def _profile_binding_digest(profile: SubAgentProfile) -> str:
    return sha256_jcs(
        {
            "profile_id": profile.profile_id,
            "provider_id": profile.provider_id,
            "audience": profile.audience,
            "goal_type": profile.goal_type,
            "capabilities": list(profile.capabilities),
            "primary_capability": profile.primary_capability,
            "required_evidence": list(profile.required_evidence),
            "scope": profile.scope,
            "value": profile.value,
            "approval": profile.approval,
            "evidence": profile.evidence,
        }
    )


def _reference_evidence_binding(
    *,
    task: TaskContract,
    action: TypedAction,
    result: ProviderResult,
    profile: SubAgentProfile,
    approval: ApprovalDecision | None,
    grant: SurfaceGrant | None,
    scene_path: str | None,
    environment_snapshot: Mapping[str, Any] | None,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    payload_material = dict(payload)
    binding: dict[str, Any] = {
        "task_id": task.task_id,
        "run_id": task.run_id,
        "action_id": action.action_id,
        "action_digest": action.action_digest,
        "approval_decision_id": approval.approval_decision_id if approval is not None else action.approval_decision_id,
        "approval_digest": approval.decision_digest if approval is not None else action.approval_digest,
        "grant_id": grant.grant_id if grant is not None else action.grant_id,
        "grant_digest": grant.grant_digest if grant is not None else action.grant_digest,
        "contract_digest": task.contract_digest,
        "project_root": task.project["root"],
        "project_fingerprint": task.project_fingerprint,
        "profile_id": profile.profile_id,
        "profile_digest": _profile_binding_digest(profile),
        "provider_ref": result.provider_ref,
        "provider_result_digest": result.provider_result_digest,
        "target": dict(action.target),
        "property_path": action.property_path,
        "expected_revision": action.expected_revision,
        "observed_revision": result.observed_revision,
        "before_value": result.before_value,
        "after_value": result.after_value,
        "payload_digest": sha256_jcs(payload_material),
        "scene_path": scene_path,
        "environment_snapshot_digest": sha256_jcs(dict(environment_snapshot)) if environment_snapshot is not None else None,
    }
    capture = payload_material.get("capture")
    if isinstance(capture, Mapping):
        capture_path = capture.get("colorPath", capture.get("color_path", capture.get("path")))
        capture_digest = capture.get("sha256", capture.get("sha256_digest", capture.get("digest")))
        if capture_path is not None:
            binding["capture_path"] = str(capture_path)
        if capture_digest is not None:
            binding["capture_digest"] = str(capture_digest)
        if capture.get("bytes") is not None:
            binding["capture_bytes"] = capture.get("bytes")
    return binding


def append_reference_evidence(
    *,
    store: Any,
    task: TaskContract,
    action: Any,
    result: ProviderResult,
    evidence: EvidenceRecord,
    evidence_type: str,
    profile: SubAgentProfile | None = None,
    approval: ApprovalDecision | None = None,
    grant: SurfaceGrant | None = None,
    scene_path: str | None = None,
    environment_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a profile-bound record through the existing durable EvidenceStore."""
    selected = profile or profile_for_task_object(task)
    if evidence.evidence_type != evidence_type or evidence.task_id != task.task_id or evidence.action_id != action.action_id:
        raise ContractValidationError("reference evidence binding mismatch")
    if evidence_type not in selected.required_evidence:
        raise ContractValidationError("reference evidence type is outside the SubAgent profile")
    if not isinstance(action, TypedAction) or not isinstance(result, ProviderResult):
        raise ContractValidationError("reference evidence requires typed action and ProviderResult")
    try:
        _validated_evidence_ids([evidence.evidence_id])
    except ContractValidationError:
        raise
    payload_material = dict(evidence.payload)
    payload_material.pop("reference_binding", None)
    if scene_path is not None:
        scene_path = canonical_scene_path(task.project["root"], scene_path, require_exists=False)
    binding = _reference_evidence_binding(
        task=task,
        action=action,
        result=result,
        profile=selected,
        approval=approval,
        grant=grant,
        scene_path=scene_path,
        environment_snapshot=environment_snapshot,
        payload=payload_material,
    )
    bound_payload = {**payload_material, "reference_binding": binding}
    bound_evidence = EvidenceRecord.observed(
        evidence_id=evidence.evidence_id,
        task_id=task.task_id,
        run_id=task.run_id,
        action_id=action.action_id,
        evidence_type=evidence_type,
        payload=bound_payload,
        profile=selected,
    )
    record = {
        "schema_version": "1.1", "evidence_id": bound_evidence.evidence_id, "run_id": task.run_id,
        "step_id": action.action_id, "source_type": selected.evidence["source_type"], "source_ref": evidence_type,
        # The evidence id is immutable.  Use the issued contract time so a
        # replay of the same run has identical content and can be confirmed as
        # idempotent by Persistence instead of colliding on wall-clock time.
        "timestamp": task.issued_at, "hash": sha256_jcs(bound_evidence.to_dict()),
        "payload_ref": f"reference://{evidence.evidence_id}",
        "producer": selected.evidence["producer"], "status": "passed", "provenance": ["runtime", selected.evidence["provenance_token"], evidence_type],
        "definition_fingerprint": reference_definition_fingerprint(), "capability": selected.primary_capability,
        "provider_ref": result.provider_ref, "project_root": task.project["root"],
        # Preserve the measured snapshot in each durable reference record.  A
        # placeholder platform flag is not an environment observation; when no
        # snapshot is available the record remains explicitly unmeasured and
        # the completion gate will still reject any mutation that requires it.
        "environment": dict(environment_snapshot) if environment_snapshot is not None else {
            "platform": "unknown", "reference_fixture": False, "measured": False,
        },
        "target": {"guid": action.target["guid"], "component_type": action.target["component_type"], "property": action.property_path},
        "safety_strength": 5, "evidence_strength": 5, "completion": "complete", "observation_state": "observed",
        "failure_class": None, "observed_evidence": [evidence_type], "required_evidence": sorted(selected.required_evidence),
        "raw_refs": [bound_evidence.evidence_id], "mutation_provenance": {
            "action_id": action.action_id,
            "action_digest": action.action_digest,
            "evidence_digest": bound_evidence.evidence_digest,
            "reference_payload": bound_evidence.payload,
            "binding": binding,
            **binding,
        },
        "latency_ms": 0, "fallback_from": None, "durability": "current_run",
    }
    return append_runtime_execution_evidence(store, record)


class EvidenceCompletionGate:
    """Runtime-only final gate; absence or uncertainty is never success."""

    def __init__(self, evidence_store: Any, approval_resolver: Any | None = None, *, profile: SubAgentProfile | None = None) -> None:
        self.evidence_store = evidence_store
        self.approval_resolver = approval_resolver
        self.profile = profile

    def validate_durable_evidence(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        grant: SurfaceGrant,
        action: TypedAction,
        result: ProviderResult,
        evidence_ids: list[str],
        scene_path: str | None = None,
        require_capture_asset: bool | None = None,
        environment_snapshot: Mapping[str, Any] | None = None,
    ) -> list[str]:
        """Validate the complete canonical binding before a mutation can commit."""
        selected = self.profile or profile_for_task_object(task)
        ids = _validated_evidence_ids(evidence_ids)
        CrossContractValidator(self.approval_resolver, profile=selected).validate(
            task=task,
            approval=approval,
            grant=grant,
            action=action,
            approval_resolver=self.approval_resolver,
            profile=selected,
        )
        ProviderPostConditionVerifier(profile=selected).verify(
            action=action,
            result=result,
            before_revision=action.expected_revision,
        )
        if not hasattr(self.evidence_store, "verify_record"):
            raise ContractValidationError("canonical EvidenceStore verification API is required")
        expected_types = set(task.required_evidence)
        found: set[str] = set()
        expected_scene = None
        if scene_path is not None:
            expected_scene = canonical_scene_path(task.project["root"], scene_path, require_exists=False)
        capture_required = (scene_path is not None) if require_capture_asset is None else require_capture_asset
        for evidence_id in ids:
            try:
                stored = self.evidence_store.verify_record(evidence_id, expected_run_id=task.run_id)
            except Exception as exc:
                raise ContractValidationError(f"durable evidence verification failed for {evidence_id}: {exc}") from exc
            provenance = stored.get("mutation_provenance")
            if not isinstance(provenance, Mapping):
                raise ContractValidationError(f"evidence {evidence_id} has no mutation provenance")
            payload = provenance.get("reference_payload")
            if not isinstance(payload, Mapping):
                raise ContractValidationError(f"evidence {evidence_id} has no canonical reference payload")
            binding = payload.get("reference_binding")
            if not isinstance(binding, Mapping):
                binding = provenance.get("binding")
            if not isinstance(binding, Mapping):
                raise ContractValidationError(f"evidence {evidence_id} has no canonical action binding")
            internal_value = {
                "schema_version": "1.1",
                "evidence_id": evidence_id,
                "task_id": task.task_id,
                "run_id": task.run_id,
                "action_id": action.action_id,
                "evidence_type": stored.get("source_ref"),
                "payload": dict(payload),
                "durability": "durable",
                "observation_state": "observed",
                "evidence_digest": provenance.get("evidence_digest"),
            }
            try:
                internal = EvidenceRecord.from_dict(internal_value, profile=selected)
            except Exception as exc:
                raise ContractValidationError(f"evidence {evidence_id} internal digest is invalid: {exc}") from exc
            if stored.get("hash") != sha256_jcs(internal.to_dict()):
                raise ContractValidationError(f"evidence {evidence_id} record hash does not match its canonical payload")
            if provenance.get("evidence_digest") != internal.evidence_digest:
                raise ContractValidationError(f"evidence {evidence_id} evidence digest binding is invalid")
            if stored.get("evidence_id") != evidence_id or stored.get("step_id") != action.action_id:
                raise ContractValidationError(f"evidence {evidence_id} step binding is invalid")
            if stored.get("verification_status") != "passed" or stored.get("observation_state") != "observed" or stored.get("durability") != "durable":
                raise ContractValidationError(f"evidence {evidence_id} is not durably observed")
            if stored.get("source_ref") not in expected_types:
                raise ContractValidationError(f"evidence {evidence_id} is outside the required evidence profile")
            if stored.get("project_root") is None or not same_project_root(str(stored.get("project_root")), task.project["root"]):
                raise ContractValidationError(f"evidence {evidence_id} project binding is invalid")
            if environment_snapshot is not None and stored.get("environment") != dict(environment_snapshot):
                raise ContractValidationError(f"evidence {evidence_id} environment snapshot binding is invalid")
            if stored.get("provider_ref") != result.provider_ref:
                raise ContractValidationError(f"evidence {evidence_id} provider binding is invalid")
            target = stored.get("target")
            if not isinstance(target, Mapping) or target.get("guid") != action.target["guid"] or target.get("component_type") != action.target["component_type"] or target.get("property") != action.property_path:
                raise ContractValidationError(f"evidence {evidence_id} target/property binding is invalid")
            expected_binding = {
                "task_id": task.task_id,
                "run_id": task.run_id,
                "action_id": action.action_id,
                "action_digest": action.action_digest,
                "approval_decision_id": approval.approval_decision_id,
                "approval_digest": approval.decision_digest,
                "grant_id": grant.grant_id,
                "grant_digest": grant.grant_digest,
                "contract_digest": task.contract_digest,
                "project_root": task.project["root"],
                "project_fingerprint": task.project_fingerprint,
                "profile_id": selected.profile_id,
                "profile_digest": _profile_binding_digest(selected),
                "provider_ref": result.provider_ref,
                "provider_result_digest": result.provider_result_digest,
                "target": dict(action.target),
                "property_path": action.property_path,
                "expected_revision": action.expected_revision,
                "observed_revision": result.observed_revision,
                "before_value": result.before_value,
                "after_value": result.after_value,
                "scene_path": expected_scene,
                "environment_snapshot_digest": sha256_jcs(dict(environment_snapshot)) if environment_snapshot is not None else None,
            }
            for key, expected in expected_binding.items():
                if binding.get(key) != expected:
                    raise ContractValidationError(f"evidence {evidence_id} binding mismatch: {key}")
            payload_material = dict(payload)
            payload_material.pop("reference_binding", None)
            if binding.get("payload_digest") != sha256_jcs(payload_material):
                raise ContractValidationError(f"evidence {evidence_id} payload digest mismatch")
            if provenance.get("action_id") != action.action_id or provenance.get("action_digest") != action.action_digest:
                raise ContractValidationError(f"evidence {evidence_id} action digest binding is invalid")
            found.add(str(stored["source_ref"]))

            if stored.get("source_ref") == "visual_capture" and capture_required:
                capture = payload_material.get("capture")
                if not isinstance(capture, Mapping):
                    raise ContractValidationError("visual_capture has no capture asset descriptor")
                capture_path = capture.get("colorPath", capture.get("color_path", capture.get("path")))
                capture_digest = capture.get("sha256", capture.get("sha256_digest", capture.get("digest")))
                if not isinstance(capture_path, str) or not isinstance(capture_digest, str):
                    raise ContractValidationError("visual_capture has no measured asset path/digest")
                project_root = Path(task.project["root"]).expanduser().resolve(strict=False)
                resolved_capture = Path(capture_path).expanduser()
                if not resolved_capture.is_absolute():
                    resolved_capture = project_root / resolved_capture
                resolved_capture = resolved_capture.resolve(strict=False)
                try:
                    resolved_capture.relative_to(project_root)
                except ValueError as exc:
                    raise ContractValidationError("visual_capture asset escapes the project root") from exc
                try:
                    asset = self.evidence_store.verify_asset(
                        resolved_capture,
                        capture_digest,
                        expected_bytes=capture.get("bytes") if isinstance(capture.get("bytes"), int) else None,
                    )
                except Exception as exc:
                    raise ContractValidationError(f"visual_capture asset verification failed: {exc}") from exc
                if binding.get("capture_digest") not in {asset["sha256"], f"sha256:{asset['sha256']}"}:
                    raise ContractValidationError("visual_capture binding digest does not match the asset")
                if binding.get("capture_path") is not None:
                    bound_path = Path(str(binding["capture_path"])).expanduser()
                    if not bound_path.is_absolute():
                        bound_path = project_root / bound_path
                    if bound_path.resolve(strict=False) != resolved_capture:
                        raise ContractValidationError("visual_capture binding path does not match the asset")
        if not set(selected.required_evidence).issubset(found):
            missing = sorted(set(selected.required_evidence) - found)
            raise ContractValidationError(f"required durable evidence is incomplete: {missing}")
        return ids

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
        profile: SubAgentProfile | None = None,
        scene_path: str | None = None,
        environment_snapshot: Mapping[str, Any] | None = None,
    ) -> CompletionProof:
        reasons: list[str] = []
        violations = list(boundary_violations or [])
        selected = profile or self.profile
        if selected is None:
            try:
                selected = profile_for_task_object(task)
            except (ProfileValidationError, ContractValidationError) as exc:
                reasons.append(str(exc))
        if approval.status != "active" or approval.human_review != "approved" or human_review != "approved":
            reasons.append("human approval is not active")
        if not actions or len(provider_results) != len(actions):
            reasons.append("final action/result cardinality is invalid")
        if selected is not None:
            validator = CrossContractValidator(self.approval_resolver, profile=selected)
            postconditions = ProviderPostConditionVerifier(profile=selected)
            for action, result in zip(actions, provider_results):
                try:
                    validator.validate(task=task, approval=approval, grant=grant, action=action, approval_resolver=self.approval_resolver, profile=selected)
                    postconditions.verify(action=action, result=result, before_revision=action.expected_revision)
                except ContractValidationError as exc:
                    reasons.append(str(exc))
        expected_evidence = set(task.required_evidence)
        evidence_by_action: dict[tuple[str, str], list[str]] = {}
        for evidence_id in evidence_ids:
            try:
                stored = self.evidence_store.get(evidence_id)
            except Exception:
                reasons.append(f"required evidence is not durable: {evidence_id}")
                continue
            provenance = stored.get("mutation_provenance") if isinstance(stored.get("mutation_provenance"), Mapping) else {}
            key = (provenance.get("action_id"), provenance.get("action_digest"))
            if key in {(item.action_id, item.action_digest) for item in actions}:
                evidence_by_action.setdefault(key, []).append(evidence_id)
            else:
                reasons.append(f"evidence binding is outside the approved action: {evidence_id}")
        if selected is not None:
            for action, result in zip(actions, provider_results):
                key = (action.action_id, action.action_digest)
                try:
                    self.validate_durable_evidence(
                        task=task,
                        approval=approval,
                        grant=grant,
                        action=action,
                        result=result,
                        evidence_ids=evidence_by_action.get(key, []),
                        scene_path=scene_path,
                        environment_snapshot=environment_snapshot,
                    )
                except (ContractValidationError, ValueError) as exc:
                    reasons.append(str(exc))
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

    @staticmethod
    def verify_persisted_run(
        *,
        run_id: str,
        persistence_root: str | Path,
        project_root: str | Path,
        scene_path: str,
        expected_before_fov: float | None = None,
        expected_after_fov: float | None = 43.0,
    ) -> dict[str, Any]:
        """Canonical, read-only verification used by Final Gate replay."""
        from Persistence.Approval.approval_store import ApprovalDecisionStore
        from Persistence.State.state_store import StateStore

        try:
            safe_id(run_id, "run_id")
        except PersistenceError as exc:
            raise ContractValidationError("persisted run id is unsafe") from exc
        root = Path(project_root).expanduser().resolve(strict=False)
        canonical_scene = canonical_scene_path(root, scene_path, require_exists=True)
        gate_store = ReferenceGateStore(persistence_root)
        state = StateStore(persistence_root).load_execution_state(run_id)
        if state.get("status") != "completed" or state.get("current_action_id") in {None, ""}:
            raise ContractValidationError("persisted run is not a completed mutation")
        state_ids = _validated_evidence_ids(state.get("evidence_refs"))
        manifest = gate_store.load_manifest(run_id)
        if manifest.get("schema_version") != "1.2":
            raise ContractValidationError("persisted reference manifest schema is not canonical")
        if manifest.get("scene_path") != canonical_scene or manifest.get("project_root") is None or not same_project_root(str(manifest["project_root"]), str(root)):
            raise ContractValidationError("persisted manifest scene/project binding is invalid")
        environment = manifest.get("environment_snapshot")
        if not isinstance(environment, Mapping):
            raise ContractValidationError("persisted run has no measured environment snapshot")
        if manifest.get("environment_snapshot_digest") != sha256_jcs(dict(environment)):
            raise ContractValidationError("persisted environment snapshot digest is invalid")
        validate_reference_environment_snapshot(environment, project_root=root, scene_path=canonical_scene)

        profile_id = manifest.get("profile_id")
        if not isinstance(profile_id, str):
            raise ContractValidationError("persisted run has no SubAgent profile binding")
        try:
            from .profiles import CATALOG
            selected = CATALOG.get(profile_id)
        except ProfileValidationError as exc:
            raise ContractValidationError(f"persisted profile is not in the canonical catalog: {profile_id}") from exc
        if manifest.get("profile_digest") != _profile_binding_digest(selected):
            raise ContractValidationError("persisted SubAgent profile digest is invalid")

        try:
            task = TaskContract.from_dict(manifest["task_contract"], profile=selected)
            approval = ApprovalDecision.from_dict(manifest["approval_decision"], profile=selected)
            grant = SurfaceGrant.from_dict(manifest["surface_grant"], profile=selected)
            action = TypedAction.from_dict(manifest["typed_action"], profile=selected)
        except (KeyError, TypeError, ValueError, ContractValidationError) as exc:
            raise ContractValidationError(f"persisted reference contracts are invalid: {exc}") from exc
        if task.run_id != run_id or approval.run_id != run_id or grant.run_id != run_id or action.run_id != run_id:
            raise ContractValidationError("persisted contracts are not bound to the requested run")
        if not same_project_root(task.project["root"], root):
            raise ContractValidationError("persisted TaskContract project is outside the requested project")
        expected_project_fingerprint = sha256_jcs({"project": task.project, "version": "reference-v1.1"})
        if task.project_fingerprint != expected_project_fingerprint or manifest.get("project_fingerprint") != task.project_fingerprint:
            raise ContractValidationError("persisted project fingerprint is invalid")
        resolver = ApprovalDecisionResolver(ApprovalDecisionStore(persistence_root), profile=selected)
        trusted_approval = resolver.resolve(approval.approval_decision_id, task=task)
        if trusted_approval.to_dict() != approval.to_dict():
            raise ContractValidationError("persisted approval differs from trusted ApprovalDecision storage")
        CrossContractValidator(resolver, profile=selected).validate(
            task=task, approval=approval, grant=grant, action=action,
            approval_resolver=resolver, profile=selected,
        )
        if state.get("current_action_id") != action.action_id:
            raise ContractValidationError("ExecutionState action binding is invalid")

        provider_data = manifest.get("provider_result")
        if not isinstance(provider_data, Mapping):
            raise ContractValidationError("persisted run has no ProviderResult")
        result = ProviderResult.from_dict(provider_data)
        ProviderPostConditionVerifier(profile=selected).verify(
            action=action, result=result, before_revision=action.expected_revision,
        )
        if expected_before_fov is not None and result.before_value != expected_before_fov:
            raise ContractValidationError("persisted ProviderResult before value is outside the requested gate")
        if expected_after_fov is not None and result.after_value != expected_after_fov:
            raise ContractValidationError("persisted ProviderResult after value is outside the requested gate")

        reservations_data = gate_store.load_reservations(run_id).get("records") or {}
        reservation_values = [ReservationRecord.from_dict(item, expected_run_id=run_id) for item in reservations_data.values()]
        committed_reservations = [item for item in reservation_values if item.state == ReservationState.COMMITTED]
        if len(committed_reservations) != 1:
            raise ContractValidationError("persisted run must contain exactly one committed reservation")
        reservation = committed_reservations[0]
        if (
            reservation.key != ActionReservationStore._key(action)
            or reservation.action_id != action.action_id
            or reservation.action_digest != action.action_digest
            or reservation.expected_revision != action.expected_revision
        ):
            raise ContractValidationError("persisted reservation action binding is invalid")
        if reservation.provider_result != result.to_dict() or reservation.evidence_ids != state_ids:
            raise ContractValidationError("persisted reservation does not bind the ProviderResult/evidence union")
        causal = reservation.causal_proof
        expected_causal = {
            "run_id": run_id,
            "action_id": action.action_id,
            "action_digest": action.action_digest,
            "provider_result_digest": result.provider_result_digest,
            "before_revision": action.expected_revision,
            "after_revision": result.observed_revision,
            "before_value": result.before_value,
            "after_value": result.after_value,
            "changed": True,
        }
        if not isinstance(causal, Mapping) or any(causal.get(key) != value for key, value in expected_causal.items()):
            raise ContractValidationError("persisted reservation has no valid this-run mutation causality proof")

        idempotency_data = gate_store.load_idempotency(run_id).get("records") or {}
        idempotency_values = [IdempotencyRecord.from_dict(item, expected_run_id=run_id) for item in idempotency_data.values()]
        committed_idempotency = [item for item in idempotency_values if item.state == ReservationState.COMMITTED]
        if len(committed_idempotency) != 1:
            raise ContractValidationError("persisted run must contain exactly one committed idempotency record")
        idempotency = committed_idempotency[0]
        if idempotency.key != IdempotencyLedger._namespace(action) or idempotency.action_digest != action.action_digest:
            raise ContractValidationError("persisted idempotency action binding is invalid")
        if idempotency.provider_result != result.to_dict() or idempotency.evidence_ids != state_ids:
            raise ContractValidationError("persisted idempotency does not bind the ProviderResult/evidence union")
        manifest_ids = _validated_evidence_ids(manifest.get("evidence_ids"))
        if manifest_ids != state_ids:
            raise ContractValidationError("persisted manifest evidence union differs from ExecutionState")

        EvidenceCompletionGate(EvidenceStore(persistence_root), resolver, profile=selected).validate_durable_evidence(
            task=task,
            approval=approval,
            grant=grant,
            action=action,
            result=result,
            evidence_ids=state_ids,
            scene_path=canonical_scene,
            require_capture_asset=True,
            environment_snapshot=environment,
        )
        return {
            "status": "passed",
            "reused": True,
            "run_id": run_id,
            "project_path": str(root),
            "scene_path": canonical_scene,
            "proof": {
                "provider_ref": result.provider_ref,
                "provider_result_digest": result.provider_result_digest,
                "action_digest": action.action_digest,
                "approval_digest": approval.decision_digest,
                "grant_digest": grant.grant_digest,
                "profile_id": selected.profile_id,
                "target_global_object_id": action.target["guid"],
                "before_fov": result.before_value,
                "after_fov": result.after_value,
                "observed_revision": result.observed_revision,
                "evidence_refs": state_ids,
                "completion_state": "eligible",
                "save_performed": False,
            },
        }


class CompletionCoordinator:
    """The only API that converts a Runtime CompletionDecision to success."""

    def present(self, proof: CompletionProof, *, ledger: RuntimeBudgetLedger) -> dict[str, Any]:
        if not isinstance(proof, CompletionProof):
            return {"status": "blocked", "completion": {"state": "blocked", "reason": "CompletionProof is required"}}
        try:
            ledger.record_parent_call()
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
