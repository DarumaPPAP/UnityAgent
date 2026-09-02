"""Production capability dispatch through the canonical Runtime Tool Broker.

The dispatcher accepts provider-independent CapabilityRequest values only. Provider
identity is selected by ToolBroker, revalidated immediately before execution, and
may change only through the existing infrastructure-only fallback policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Guardrails.tool_runtime_guard import guard_runtime_dispatch
from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.fallback_policy import FallbackPolicy

ProviderExecutor = Callable[
    [dict[str, Any], ResolutionContext, Mapping[str, Any]],
    dict[str, Any],
]


@dataclass(frozen=True)
class DispatchAttempt:
    provider_ref: str
    status: str
    failure_class: str | None
    fallback_from: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_ref": self.provider_ref,
            "status": self.status,
            "failure_class": self.failure_class,
            "fallback_from": self.fallback_from,
        }


def _failure(provider_ref: str, failure_class: str, reason: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_class": failure_class,
        "reason": reason,
        "provider_ref": provider_ref,
        "evidence": [],
    }


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    if hasattr(snapshot, "to_dict"):
        value = snapshot.to_dict()
    else:
        value = snapshot
    if not isinstance(value, dict):
        raise ValueError("environment snapshot must be a mapping or EnvironmentSnapshot")
    return value


def _invoke_executor(
    executor: ProviderExecutor | None,
    *,
    provider_ref: str,
    request: dict[str, Any],
    context: ResolutionContext,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    if executor is None:
        return _failure(
            provider_ref,
            "backend_not_implemented",
            "resolved provider has no registered Production executor for this runtime",
        )
    try:
        result = executor(request, context, arguments)
    except TimeoutError:
        return _failure(provider_ref, "timeout", "provider executor timed out")
    except PermissionError:
        return _failure(provider_ref, "unavailable", "provider executor is not permitted")
    except (ConnectionError, OSError) as exc:
        return _failure(provider_ref, "unhealthy", f"provider executor transport failed: {exc}")
    except Exception as exc:  # Provider adapter defect is not infrastructure fallback evidence.
        return _failure(provider_ref, "execution_failed", f"provider executor failed: {exc}")

    if not isinstance(result, dict):
        return _failure(provider_ref, "not_observed", "provider executor did not return structured data")
    result_provider = result.get("provider_ref")
    if result_provider is not None and str(result_provider) != provider_ref:
        return _failure(
            provider_ref,
            "ambiguous_binding",
            "ProviderResult provider_ref does not match Tool Broker resolution",
        )
    status = str(result.get("status") or "")
    if status not in {"passed", "failed", "not_applicable"}:
        return _failure(provider_ref, "not_observed", "ProviderResult status is not canonical")
    if status == "failed" and not result.get("failure_class"):
        return _failure(provider_ref, "not_observed", "failed ProviderResult is missing failure_class")
    if status != "failed" and result.get("failure_class") is not None:
        return _failure(provider_ref, "execution_failed", "non-failed ProviderResult carried failure_class")
    return {**result, "provider_ref": provider_ref}


def dispatch_capability(
    broker: Any,
    request: dict[str, Any],
    environment_snapshot: Any,
    *,
    context: ResolutionContext,
    executors: Mapping[str, ProviderExecutor],
    provider_arguments: Mapping[str, Mapping[str, Any]] | None = None,
    maximum_retry_attempts: int = 1,
) -> dict[str, Any]:
    """Resolve and execute one capability without accepting caller-selected Provider identity."""
    validate_capability_request(request)
    snapshot = _snapshot_dict(environment_snapshot)
    validate_environment_snapshot(snapshot)
    if not isinstance(executors, Mapping):
        raise ValueError("executors must be a provider-id mapping")

    guard = guard_runtime_dispatch(request, snapshot, context=context)
    if not guard.allowed:
        return {
            "schema_version": "1.0",
            "status": "blocked",
            "capability": request["capability"],
            "resolution": None,
            "provider_result": _failure("", str(guard.failure_class), str(guard.reason)),
            "attempts": [],
            "fallback_from": None,
        }

    resolution = broker.resolve(request, environment_snapshot, context=context)
    if resolution.get("status") != "resolved":
        return {
            "schema_version": "1.0",
            "status": "blocked",
            "capability": request["capability"],
            "resolution": resolution,
            "provider_result": {
                "status": "failed",
                "failure_class": resolution.get("failure_class"),
                "reason": resolution.get("reason"),
                "provider_ref": None,
                "evidence": [],
            },
            "attempts": [],
            "fallback_from": None,
        }

    fallback = FallbackPolicy(
        broker=broker,
        maximum_retry_attempts=maximum_retry_attempts,
    )
    arguments_by_provider = provider_arguments or {}
    attempts: list[DispatchAttempt] = []
    fallback_from: str | None = None
    current_resolution = resolution

    # Candidate count plus bounded same-provider retries gives a finite hard ceiling.
    hard_attempt_limit = max(1, len(executors) + maximum_retry_attempts + 2)
    for _ in range(hard_attempt_limit):
        provider_ref = str(current_resolution.get("provider_ref") or "")
        if not provider_ref:
            break

        # Project/Policy/Approval/Scope are observed again at the last possible boundary.
        guard = guard_runtime_dispatch(
            request,
            snapshot,
            context=context,
            original_request=request,
        )
        if not guard.allowed:
            provider_result = _failure(provider_ref, str(guard.failure_class), str(guard.reason))
            attempts.append(
                DispatchAttempt(provider_ref, "failed", provider_result["failure_class"], fallback_from)
            )
            return {
                "schema_version": "1.0",
                "status": "blocked",
                "capability": request["capability"],
                "resolution": current_resolution,
                "provider_result": provider_result,
                "attempts": [item.to_dict() for item in attempts],
                "fallback_from": fallback_from,
            }

        executor = executors.get(provider_ref)
        arguments = arguments_by_provider.get(provider_ref) or {}
        provider_result = _invoke_executor(
            executor,
            provider_ref=provider_ref,
            request=request,
            context=context,
            arguments=arguments,
        )
        attempts.append(
            DispatchAttempt(
                provider_ref,
                str(provider_result.get("status") or "failed"),
                provider_result.get("failure_class"),
                fallback_from,
            )
        )
        if provider_result.get("status") in {"passed", "not_applicable"}:
            return {
                "schema_version": "1.0",
                "status": "completed",
                "capability": request["capability"],
                "resolution": current_resolution,
                "provider_result": provider_result,
                "attempts": [item.to_dict() for item in attempts],
                "fallback_from": fallback_from,
            }

        decision = fallback.after_failure(
            request,
            environment_snapshot,
            context=context,
            previous_provider_id=provider_ref,
            provider_result=provider_result,
            original_request=request,
        )
        action = decision.get("action")
        if action == "retry_same_provider":
            continue
        if action == "fallback" and decision.get("status") == "resolved":
            fallback_from = provider_ref
            current_resolution = {
                "schema_version": decision["schema_version"],
                "capability": decision["capability"],
                "status": decision["status"],
                "provider_ref": decision["provider_ref"],
                "observed_surface": decision["observed_surface"],
                "evidence_supported": list(decision.get("evidence_supported") or []),
                "failure_class": decision.get("failure_class"),
                "reason": decision.get("reason"),
            }
            continue

        final_status = "partial" if decision.get("status") == "partial" else "blocked"
        return {
            "schema_version": "1.0",
            "status": final_status,
            "capability": request["capability"],
            "resolution": current_resolution,
            "provider_result": provider_result,
            "attempts": [item.to_dict() for item in attempts],
            "fallback_from": fallback_from,
            "fallback_decision": decision,
        }

    return {
        "schema_version": "1.0",
        "status": "blocked",
        "capability": request["capability"],
        "resolution": current_resolution,
        "provider_result": _failure(
            str(current_resolution.get("provider_ref") or ""),
            "execution_failed",
            "Production dispatch attempt ceiling was reached",
        ),
        "attempts": [item.to_dict() for item in attempts],
        "fallback_from": fallback_from,
    }
