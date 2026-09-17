"""UnityAgent-owned planning, approval projection and budget accounting."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import threading
import time
import uuid
from typing import Any, Mapping

from Persistence.Store.atomic_store import PersistenceError

from .canonicalization import digest_for
from .contracts import (
    ApprovalDecision,
    ContractValidationError,
    SurfaceGrant,
    TaskContract,
)
from .profiles import ProfileValidationError, SubAgentProfile, profile_for_task_object


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
    _measured_token_dimensions: set[str] = field(default_factory=set, init=False, repr=False)

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
        self._measured_token_dimensions = {
            name for name in ("parent_input_tokens", "parent_output_tokens", "child_input_tokens", "child_output_tokens")
            if name in self._counts and self._counts[name] != 0
        }

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

    def record_parent_call(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        elapsed_ms: float = 0.0,
        context_bytes: int = 0,
        schema_bytes: int = 0,
    ) -> dict[str, int]:
        """Record one observed parent turn through the authoritative ledger."""
        self.consume("parent_total_calls", 1)
        self._record_tokens("parent_input_tokens", input_tokens)
        self._record_tokens("parent_output_tokens", output_tokens)
        return self.record_observation(
            elapsed_ms=elapsed_ms,
            context_bytes=context_bytes,
            schema_bytes=schema_bytes,
        )

    def record_child_llm_call(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        elapsed_ms: float = 0.0,
        context_bytes: int = 0,
        schema_bytes: int = 0,
    ) -> dict[str, int]:
        """Record a specialist model call; the Runtime still owns the budget."""
        self.consume("child_llm_calls", 1)
        self._record_tokens("child_input_tokens", input_tokens)
        self._record_tokens("child_output_tokens", output_tokens)
        return self.record_observation(
            elapsed_ms=elapsed_ms,
            child_elapsed_ms=elapsed_ms,
            context_bytes=context_bytes,
            schema_bytes=schema_bytes,
        )

    def record_child_observation(
        self,
        *,
        elapsed_ms: float,
        context_bytes: int = 0,
        schema_bytes: int = 0,
    ) -> dict[str, int]:
        """Record measured bounded child/provider time without inventing tokens."""
        return self.record_observation(
            elapsed_ms=elapsed_ms,
            child_elapsed_ms=elapsed_ms,
            context_bytes=context_bytes,
            schema_bytes=schema_bytes,
        )

    def record_tool_call(self, *, elapsed_ms: float = 0.0) -> dict[str, int]:
        self.consume("tool_calls", 1)
        return self.record_observation(elapsed_ms=elapsed_ms)

    def _record_tokens(self, counter: str, amount: int | None) -> None:
        if amount is None:
            return
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ContractValidationError(f"{counter} must be a non-negative integer or None")
        self.consume(counter, amount)
        with self._lock:
            self._measured_token_dimensions.add(counter)

    def record_observation(
        self,
        *,
        elapsed_ms: float = 0.0,
        child_elapsed_ms: float = 0.0,
        context_bytes: int = 0,
        schema_bytes: int = 0,
    ) -> dict[str, int]:
        values = {
            "elapsed_ms": elapsed_ms,
            "child_elapsed_ms": child_elapsed_ms,
            "context_bytes": context_bytes,
            "schema_bytes": schema_bytes,
        }
        for name, raw in values.items():
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)) or float(raw) < 0:
                raise ContractValidationError(f"{name} must be a non-negative finite number")
        wall = max(0, int(math.ceil(float(elapsed_ms))))
        child_wall = max(0, int(math.ceil(float(child_elapsed_ms))))
        # Measurement counters are deliberately committed through the same
        # hard budget checks as every other Runtime counter.
        if wall:
            self.consume("wall_clock_ms", wall)
        if child_wall:
            self.consume("child_wall_clock_ms", child_wall)
        if context_bytes:
            self.consume("context_bytes", int(context_bytes))
        if schema_bytes:
            self.consume("schema_bytes", int(schema_bytes))
        return self.snapshot()

    def measurement_snapshot(self) -> dict[str, Any]:
        values = self.snapshot()
        token_dimensions = (
            "parent_input_tokens", "parent_output_tokens", "child_input_tokens", "child_output_tokens"
        )
        measured_dimensions = {
            name: name in self._measured_token_dimensions for name in token_dimensions
        }
        if all(measured_dimensions.values()):
            token_status = "measured"
        elif any(measured_dimensions.values()):
            token_status = "partial"
        else:
            token_status = "unmeasured"

        def token_value(name: str) -> int | None:
            return values[name] if measured_dimensions[name] else None

        return {
            "measured": token_status == "measured",
            "token_measurement": {"status": token_status, "dimensions": measured_dimensions},
            "parent": {
                "calls": values["parent_total_calls"],
                "input_tokens": token_value("parent_input_tokens"),
                "output_tokens": token_value("parent_output_tokens"),
            },
            "child": {
                "llm_calls": values["child_llm_calls"],
                "input_tokens": token_value("child_input_tokens"),
                "output_tokens": token_value("child_output_tokens"),
                "wall_clock_ms": values["child_wall_clock_ms"],
            },
            "wall_clock_ms": values["wall_clock_ms"],
            "context_bytes": values["context_bytes"],
            "schema_bytes": values["schema_bytes"],
            "parent_per_tool_mediation": 0,
        }

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
        profile: SubAgentProfile | None = None,
    ) -> TaskContract:
        return TaskContract.issue(
            task_id=task_id,
            run_id=run_id,
            project=project,
            project_fingerprint=project_fingerprint,
            issued_at=issued_at or iso_now(),
            budgets=budgets,
            scope=scope,
            profile=profile,
        )


class SubAgentTaskPlanner:
    """Creates one bounded specialist plan and never performs Provider work."""

    def plan(self, task: TaskContract, ledger: RuntimeBudgetLedger, *, profile: SubAgentProfile | None = None) -> dict[str, Any]:
        selected = profile or profile_for_task_object(task)
        started = time.perf_counter()
        ledger.record_parent_call(elapsed_ms=(time.perf_counter() - started) * 1000)
        return {
            "schema_version": "1.1",
            "task_id": task.task_id,
            "run_id": task.run_id,
            "goal_type": task.goal_type,
            "specialist": selected.display_name,
            "subagent_profile_id": selected.profile_id,
            "provider_id": selected.provider_id,
            "steps": ["inspect", "propose_typed_action", "await_runtime_result", "evaluate"],
            "provider_resolution_owner": "Runtime.ToolBroker",
            "parent_per_tool_mediation": 0,
        }


class ApprovalDecisionResolver:
    """Trusted lookup boundary for persisted approval decisions."""

    def __init__(self, store: Any | None = None, profile: SubAgentProfile | None = None) -> None:
        self.store = store
        self.profile = profile
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
                decision = ApprovalDecision.from_dict(record["decision"], profile=self.profile)
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
    """Projects approval into the smallest authenticated profile surface."""

    def derive(
        self,
        *,
        task: TaskContract,
        approval: ApprovalDecision,
        subagent_instance_id: str,
        requested_capabilities: list[str] | None = None,
        now: datetime | None = None,
        profile: SubAgentProfile | None = None,
    ) -> SurfaceGrant:
        selected = profile or profile_for_task_object(task)
        current = now or utc_now()
        if approval.task_id != task.task_id or approval.contract_digest != task.contract_digest:
            raise ContractValidationError("cannot grant an approval for another TaskContract")
        if _as_datetime(approval.expires_at) <= current:
            raise ContractValidationError("cannot grant an expired approval")
        requested = requested_capabilities or list(selected.capabilities)
        try:
            selected.validate_capabilities(requested)
        except ProfileValidationError as exc:
            raise ContractValidationError(f"requested capability is outside the SubAgent profile: {exc}") from exc
        issued = current.isoformat()
        value = {
            "schema_version": "1.1", "grant_id": f"grant-{uuid.uuid4().hex}", "audience": selected.audience,
            "subagent_instance_id": subagent_instance_id, "task_id": task.task_id, "run_id": task.run_id,
            "project": dict(task.project), "project_fingerprint": task.project_fingerprint,
            "contract_digest": task.contract_digest, "approval_decision_id": approval.approval_decision_id,
            "approval_digest": approval.decision_digest, "capabilities": list(dict.fromkeys(requested)),
            "issued_at": issued, "expires_at": approval.expires_at, "revocation_epoch": approval.revocation_epoch,
        }
        value["grant_digest"] = digest_for(value, "grant_digest")
        return SurfaceGrant.from_dict(value, profile=selected)


class ParentCompletionGuard:
    """Keeps the parent's second call a presentation of Runtime truth only."""

    def __init__(self, ledger: RuntimeBudgetLedger) -> None:
        self.ledger = ledger

    def record_completion_call(self) -> None:
        self.ledger.record_parent_call()

    def assert_no_per_tool_mediation(self, plan: Mapping[str, Any]) -> None:
        if plan.get("parent_per_tool_mediation") != 0:
            raise ContractValidationError("parent per-tool mediation is forbidden")
