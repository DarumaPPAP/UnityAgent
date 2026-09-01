"""Infrastructure-only fallback policy for the Runtime Tool Broker.

Fallback never changes task semantics. It may retry a retryable infrastructure
failure within a bounded budget or ask the existing Runtime resolver for another
provider for the exact same CapabilityRequest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Guardrails.tool_runtime_guard import guard_runtime_dispatch
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.provider_contract import ProviderRegistry
from Runtime.Tooling.provider_registry import RuntimeProviderRegistry
from Runtime.Tooling.safety_strength import compare_fallback_strength
from Runtime.Tooling.tool_broker import ToolBroker

RETRYABLE_INFRA_FAILURES = frozenset({"unhealthy", "timeout"})
RERESOLVE_FAILURES = frozenset(
    {"unavailable", "unsupported", "backend_not_implemented"}
)
PARTIAL_FAILURES = frozenset({"unknown", "not_observed"})
TERMINAL_FAILURES = frozenset(
    {
        "ambiguous_binding",
        "blocked_by_policy",
        "blocked_by_approval",
        "scope_violation",
        "precondition_failed",
        "execution_failed",
        "cancelled",
        "observed_test_failure",
    }
)


@dataclass(frozen=True)
class FailureDisposition:
    action: str
    failure_class: str
    reason: str


@dataclass
class RetryBudget:
    """Current-run bounded retry counter; never durable state."""

    maximum_attempts: int = 1
    attempts_used: int = 0

    def __post_init__(self) -> None:
        if self.maximum_attempts < 0 or self.maximum_attempts > 3:
            raise ValueError("maximum_attempts must be between 0 and 3")

    def consume(self) -> bool:
        if self.attempts_used >= self.maximum_attempts:
            return False
        self.attempts_used += 1
        return True


def classify_provider_failure(
    failure_class: str | None,
    *,
    retry_budget: RetryBudget | None = None,
) -> FailureDisposition:
    """Classify only transport/infrastructure recovery; no semantic replan."""
    value = str(failure_class or "unknown")
    if value in RETRYABLE_INFRA_FAILURES:
        if retry_budget is not None and retry_budget.consume():
            return FailureDisposition(
                "retry_same_provider",
                value,
                "retryable infrastructure failure within bounded retry budget",
            )
        return FailureDisposition(
            "reresolve",
            value,
            "retryable infrastructure budget exhausted; re-query same capability",
        )
    if value in RERESOLVE_FAILURES:
        return FailureDisposition(
            "reresolve",
            value,
            "provider cannot currently satisfy the same capability",
        )
    if value in PARTIAL_FAILURES:
        return FailureDisposition(
            "partial",
            value,
            "capability was not proven; preserve as explicit partial/not-observed state",
        )
    if value in TERMINAL_FAILURES:
        return FailureDisposition(
            "stop",
            value,
            "failure is not an infrastructure fallback trigger",
        )
    return FailureDisposition(
        "stop",
        value,
        "unknown failure class is fail-closed",
    )


def _normalized_scope(request: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    scope = request.get("mutation_scope")
    if scope is None:
        return None
    if not isinstance(scope, dict):
        return ((), ("<invalid>",))
    allowed = tuple(sorted(str(item) for item in scope.get("allowed_paths") or []))
    prohibited = tuple(sorted(str(item) for item in scope.get("prohibited_paths") or []))
    return allowed, prohibited


def execution_contract_unchanged(
    original_request: dict[str, Any],
    fallback_request: dict[str, Any],
) -> tuple[bool, str | None]:
    """Reject semantic/evidence/scope changes while performing infrastructure fallback."""
    validate_capability_request(original_request)
    validate_capability_request(fallback_request)
    if original_request["capability"] != fallback_request["capability"]:
        return False, "fallback changed capability"
    if not same_project_root(
        str(original_request["project_root"]),
        str(fallback_request["project_root"]),
    ):
        return False, "fallback changed project root"
    if original_request["operation_kind"] != fallback_request["operation_kind"]:
        return False, "fallback changed operation kind"
    if set(original_request["required_evidence"]) != set(
        fallback_request["required_evidence"]
    ):
        return False, "fallback changed required evidence"
    if _normalized_scope(original_request) != _normalized_scope(fallback_request):
        return False, "fallback changed or expanded mutation scope"
    if original_request.get("approval_ref") != fallback_request.get("approval_ref"):
        return False, "fallback changed approval reference"
    return True, None


class FallbackPolicy:
    """Bounded fallback coordination over the canonical ToolBroker."""

    def __init__(
        self,
        *,
        broker: ToolBroker | None = None,
        registry: ProviderRegistry | RuntimeProviderRegistry | None = None,
        maximum_retry_attempts: int = 1,
    ) -> None:
        self._registry = (
            registry
            if isinstance(registry, RuntimeProviderRegistry)
            else RuntimeProviderRegistry(registry=registry)
        )
        self._broker = broker or ToolBroker(self._registry)
        self.retry_budget = RetryBudget(maximum_retry_attempts)

    def after_failure(
        self,
        request: dict[str, Any],
        environment_snapshot: Any,
        *,
        context: ResolutionContext,
        previous_provider_id: str,
        provider_result: dict[str, Any],
        original_request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        baseline = original_request or request
        try:
            unchanged, reason = execution_contract_unchanged(baseline, request)
        except Exception as exc:
            return {
                "status": "blocked",
                "failure_class": "precondition_failed",
                "reason": f"invalid fallback contract: {exc}",
                "provider_ref": None,
                "action": "stop",
                "evidence": [],
            }
        if not unchanged:
            return {
                "status": "blocked",
                "failure_class": "scope_violation"
                if "scope" in str(reason)
                else "precondition_failed",
                "reason": reason,
                "provider_ref": None,
                "action": "stop",
                "evidence": [],
            }

        snapshot_value = (
            environment_snapshot.to_dict()
            if hasattr(environment_snapshot, "to_dict")
            else environment_snapshot
        )
        guard = guard_runtime_dispatch(
            request,
            snapshot_value,
            context=context,
            original_request=baseline,
        )
        if not guard.allowed:
            return {
                "status": "blocked",
                "failure_class": guard.failure_class,
                "reason": guard.reason,
                "provider_ref": None,
                "action": "stop",
                "evidence": [],
            }

        disposition = classify_provider_failure(
            provider_result.get("failure_class"),
            retry_budget=self.retry_budget,
        )
        if disposition.action == "retry_same_provider":
            return {
                "status": "retry",
                "failure_class": disposition.failure_class,
                "reason": disposition.reason,
                "provider_ref": previous_provider_id,
                "action": disposition.action,
                "evidence": [],
            }
        if disposition.action == "partial":
            return {
                "status": "partial",
                "failure_class": disposition.failure_class,
                "reason": disposition.reason,
                "provider_ref": None,
                "action": disposition.action,
                "evidence": [],
                "verified": False,
            }
        if disposition.action == "stop":
            return {
                "status": "blocked",
                "failure_class": disposition.failure_class,
                "reason": disposition.reason,
                "provider_ref": None,
                "action": disposition.action,
                "evidence": [],
            }

        resolution = self._broker.resolve_fallback(
            request,
            environment_snapshot,
            context=context,
            previous_provider_id=previous_provider_id,
        )
        if resolution.get("status") != "resolved":
            return {
                **resolution,
                "action": "stop",
                "evidence": [],
            }

        candidate_id = str(resolution["provider_ref"])
        check = compare_fallback_strength(
            capability=str(request["capability"]),
            previous_provider_id=previous_provider_id,
            candidate_provider_id=candidate_id,
            required_evidence=request.get("required_evidence") or (),
            registry=self._registry,
        )
        if not check.allowed:
            return {
                "status": check.failure_class or "unsupported",
                "failure_class": check.failure_class or "unsupported",
                "reason": check.reason,
                "provider_ref": None,
                "action": "stop",
                "evidence": [],
            }
        return {
            **resolution,
            "action": "fallback",
            "fallback_from_provider_ref": previous_provider_id,
            "strength_check": {
                "previous_safety": check.previous_safety,
                "candidate_safety": check.candidate_safety,
                "previous_evidence": check.previous_evidence,
                "candidate_evidence": check.candidate_evidence,
            },
        }


def compose_partial_completion(
    *,
    completed_results: Iterable[dict[str, Any]],
    unresolved_capability: str,
    unresolved_result: dict[str, Any],
) -> dict[str, Any]:
    """Preserve useful completed facts without claiming unresolved work succeeded."""
    completed = list(completed_results)
    evidence: list[str] = []
    for result in completed:
        if result.get("status") != "passed":
            continue
        for item in result.get("evidence") or []:
            value = str(item)
            if value not in evidence:
                evidence.append(value)
    return {
        "status": "partial",
        "verified": False,
        "completed_count": sum(1 for item in completed if item.get("status") == "passed"),
        "unresolved_capability": unresolved_capability,
        "unresolved_status": unresolved_result.get("status"),
        "unresolved_failure_class": unresolved_result.get("failure_class"),
        "evidence": evidence,
    }
