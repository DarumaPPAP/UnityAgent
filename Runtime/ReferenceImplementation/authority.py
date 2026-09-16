"""UnityAgent-owned planning, approval projection and budget accounting."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
import uuid
from typing import Any, Mapping

from Persistence.Store.atomic_store import PersistenceError

from .canonicalization import digest_for
from .contracts import (
    ALLOWED_CAPABILITIES,
    ApprovalDecision,
    ContractValidationError,
    SurfaceGrant,
    TaskContract,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def _as_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class RuntimeBudgetLedger:
    """Authoritative counters; Runtime, not a model, decides exhaustion."""

    limits: dict[str, int]
    _counts: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    COUNTERS = (
        "parent_total_calls", "parent_reentries", "global_replans", "escalations", "child_llm_calls",
        "child_input_tokens", "child_output_tokens", "parent_input_tokens", "parent_output_tokens",
        "tool_calls", "wall_clock_ms", "child_wall_clock_ms", "context_bytes", "schema_bytes",
        "provider_retries", "process_restarts",
    )
    LIMIT_TO_COUNTER = {
        "max_parent_total_calls": "parent_total_calls", "max_parent_reentries": "parent_reentries",
        "max_global_replans": "global_replans", "max_escalations": "escalations", "max_child_llm_calls": "child_llm_calls",
        "max_child_input_tokens": "child_input_tokens", "max_child_output_tokens": "child_output_tokens",
        "max_parent_input_tokens": "parent_input_tokens", "max_parent_output_tokens": "parent_output_tokens",
        "max_tool_calls": "tool_calls", "max_wall_clock_ms": "wall_clock_ms", "max_child_wall_clock_ms": "child_wall_clock_ms",
        "max_provider_retries": "provider_retries", "max_process_restarts": "process_restarts",
    }

    def __post_init__(self) -> None:
        self._counts = {name: int(self._counts.get(name, 0)) for name in self.COUNTERS}

    def consume(self, counter: str, amount: int = 1) -> dict[str, int]:
        if counter not in self.COUNTERS:
            raise ContractValidationError(f"unknown budget counter: {counter}")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ContractValidationError("budget increment must be a non-negative integer")
        with self._lock:
            proposed = self._counts[counter] + amount
            limit = next((self.limits[key] for key, name in self.LIMIT_TO_COUNTER.items() if name == counter), None)
            if limit is not None and proposed > limit:
                raise BudgetExceeded(f"budget exceeded: {counter} {proposed}>{limit}")
            self._counts[counter] = proposed
            return dict(self._counts)

    def add_unbounded(self, counter: str, amount: int = 1) -> dict[str, int]:
        if counter not in self.COUNTERS:
            raise ContractValidationError(f"unknown budget counter: {counter}")
        with self._lock:
            self._counts[counter] += amount
            return dict(self._counts)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def within_limits(self) -> bool:
        values = self.snapshot()
        return all(values[counter] <= self.limits[limit] for limit, counter in self.LIMIT_TO_COUNTER.items())

    @property
    def exhausted(self) -> bool:
        return not self.within_limits()


class BudgetExceeded(RuntimeError):
    """A Runtime budget prevented further work."""


class BudgetEnforcer:
    def __init__(self, ledger: RuntimeBudgetLedger) -> None:
        self.ledger = ledger

    def allow(self, counter: str, amount: int = 1) -> bool:
        try:
            self.ledger.consume(counter, amount)
        except BudgetExceeded:
            return False
        return True

    def require(self, counter: str, amount: int = 1) -> None:
        self.ledger.consume(counter, amount)


class TaskContractIssuer:
    def issue(
        self,
        *,
        task_id: str,
        run_id: str,
        project: dict[str, str],
        project_fingerprint: str,
        budgets: dict[str, int],
        scope: dict[str, Any] | None = None,
        issued_at: str | None = None,
    ) -> TaskContract:
        return TaskContract.issue(
            task_id=task_id,
            run_id=run_id,
            project=project,
            project_fingerprint=project_fingerprint,
            issued_at=issued_at or iso_now(),
            budgets=budgets,
            scope=scope,
        )


class SubAgentTaskPlanner:
    """Creates one bounded specialist plan and never performs Provider work."""

    def plan(self, task: TaskContract, ledger: RuntimeBudgetLedger) -> dict[str, Any]:
        ledger.consume("parent_total_calls", 1)
        return {
            "schema_version": "1.1",
            "task_id": task.task_id,
            "run_id": task.run_id,
            "goal_type": task.goal_type,
            "specialist": "UnityArtistCLI",
            "steps": ["inspect", "propose_typed_action", "await_runtime_result", "evaluate"],
            "provider_resolution_owner": "Runtime.ToolBroker",
            "parent_per_tool_mediation": 0,
        }


class ApprovalDecisionResolver:
    """Trusted lookup boundary for persisted approval decisions."""

    def __init__(self, store: Any | None = None) -> None:
        self.store = store
        self._decisions: dict[str, ApprovalDecision] = {}
        self._revocation_epochs: dict[str, int] = {}
        self._lock = threading.RLock()

    def register(self, decision: ApprovalDecision) -> None:
        with self._lock:
            self._decisions[decision.approval_decision_id] = decision
            self._revocation_epochs[decision.approval_decision_id] = decision.revocation_epoch
            if self.store is not None:
                self.store.register(decision)

    def revoke(self, approval_decision_id: str) -> None:
        with self._lock:
            if self.store is not None:
                current = self.store.revoke(approval_decision_id)
                self._revocation_epochs[approval_decision_id] = current
                return
            decision = self._decisions.get(approval_decision_id)
            if decision is None:
                raise ContractValidationError("unknown approval decision")
            self._revocation_epochs[approval_decision_id] = decision.revocation_epoch + 1

    def resolve(self, approval_decision_id: str, *, task: TaskContract, now: datetime | None = None) -> ApprovalDecision:
        with self._lock:
            if self.store is not None:
                try:
                    record = self.store.get(approval_decision_id)
                except PersistenceError as exc:
                    raise ContractValidationError(
                        f"approval decision could not be resolved from trusted storage: {exc.code}"
                    ) from exc
                decision = ApprovalDecision.from_dict(record["decision"])
                current_epoch = int(record.get("current_revocation_epoch", decision.revocation_epoch))
            else:
                decision = self._decisions.get(approval_decision_id)
                current_epoch = self._revocation_epochs.get(approval_decision_id)
        if decision is None:
            raise ContractValidationError("approval decision was not found in trusted storage")
        if decision.task_id != task.task_id or decision.run_id != task.run_id:
            raise ContractValidationError("approval decision does not bind to TaskContract")
        if decision.project_fingerprint != task.project_fingerprint or decision.contract_digest != task.contract_digest:
            raise ContractValidationError("approval decision project/contract binding mismatch")
        if decision.status != "active" or decision.human_review != "approved":
            raise ContractValidationError("approval decision is not active and approved")
        if current_epoch != decision.revocation_epoch:
            raise ContractValidationError("approval decision has been revoked")
        if _as_datetime(decision.expires_at) <= (now or utc_now()):
            raise ContractValidationError("approval decision has expired")
        return decision


class SurfaceGrantProjector:
    """Projects approval into the smallest authenticated Artist capability surface."""

    def derive(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        subagent_instance_id: str,
        requested_capabilities: list[str] | None = None,
        now: datetime | None = None,
    ) -> SurfaceGrant:
        current = now or utc_now()
        if approval.task_id != task.task_id or approval.contract_digest != task.contract_digest:
            raise ContractValidationError("cannot grant an approval for another TaskContract")
        if _as_datetime(approval.expires_at) <= current:
            raise ContractValidationError("cannot grant an expired approval")
        requested = requested_capabilities or ["artist.camera.inspect", "artist.camera.refine", "visual.capture"]
        if not requested or any(item not in ALLOWED_CAPABILITIES for item in requested):
            raise ContractValidationError("requested Artist capability is outside the v1 allowlist")
        if "artist.camera.refine" not in requested:
            raise ContractValidationError("Camera FOV specialist grant must include artist.camera.refine")
        issued = current.isoformat()
        value = {
            "schema_version": "1.1", "grant_id": f"grant-{uuid.uuid4().hex}", "audience": "unity_artist",
            "subagent_instance_id": subagent_instance_id, "task_id": task.task_id, "run_id": task.run_id,
            "project": dict(task.project), "project_fingerprint": task.project_fingerprint,
            "contract_digest": task.contract_digest, "approval_decision_id": approval.approval_decision_id,
            "approval_digest": approval.decision_digest, "capabilities": list(dict.fromkeys(requested)),
            "issued_at": issued, "expires_at": approval.expires_at, "revocation_epoch": approval.revocation_epoch,
        }
        value["grant_digest"] = digest_for(value, "grant_digest")
        return SurfaceGrant.from_dict(value)


class ParentCompletionGuard:
    """Keeps the parent's second call a presentation of Runtime truth only."""

    def __init__(self, ledger: RuntimeBudgetLedger) -> None:
        self.ledger = ledger

    def record_completion_call(self) -> None:
        self.ledger.consume("parent_total_calls", 1)

    def assert_no_per_tool_mediation(self, plan: Mapping[str, Any]) -> None:
        if plan.get("parent_per_tool_mediation") != 0:
            raise ContractValidationError("parent per-tool mediation is forbidden")
