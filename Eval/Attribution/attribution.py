"""Canonical Eval failure attribution and quality-denominator policy."""
from __future__ import annotations

from typing import Any, Mapping

AGENT_FAILURES = {"agent_behavior_regression"}
RUNTIME_INFRA_FAILURES = {
    "runtime_timeout",
    "runtime_protocol_failure",
    "runtime_cancelled",
    "runtime_tool_unavailable",
}
POLICY_OR_PERMISSION_FAILURES = {"runtime_permission_denied"}
EVALUATOR_INFRA_FAILURES = {"evaluator_contract_failure"}
FIXTURE_FAILURES = {"task_fixture_invalid"}
UNAVAILABLE_EVIDENCE_FAILURES = {"unavailable_required_evidence"}
KNOWN_FAILURES = (
    AGENT_FAILURES
    | RUNTIME_INFRA_FAILURES
    | POLICY_OR_PERMISSION_FAILURES
    | EVALUATOR_INFRA_FAILURES
    | FIXTURE_FAILURES
    | UNAVAILABLE_EVIDENCE_FAILURES
)

PROVIDER_ENVIRONMENT_FAILURES = {
    "unavailable",
    "unknown",
    "unhealthy",
    "ambiguous_binding",
    "unsupported",
    "backend_not_implemented",
    "precondition_failed",
}
PROVIDER_POLICY_FAILURES = {
    "blocked_by_policy",
    "blocked_by_approval",
    "scope_violation",
}
PROVIDER_OBSERVED_PRODUCT_FAILURES = {
    "execution_failed",
    "observed_test_failure",
}
PROVIDER_UNAVAILABLE_EVIDENCE_FAILURES = {"not_observed"}
PROVIDER_KNOWN_FAILURES = (
    PROVIDER_ENVIRONMENT_FAILURES
    | PROVIDER_POLICY_FAILURES
    | PROVIDER_OBSERVED_PRODUCT_FAILURES
    | PROVIDER_UNAVAILABLE_EVIDENCE_FAILURES
    | {"timeout", "cancelled"}
)


class AttributionError(ValueError):
    pass


def classify_failure(failure_class: str | None) -> str:
    if failure_class is None:
        return "none"
    if failure_class not in KNOWN_FAILURES:
        raise AttributionError(f"unsupported typed failure_class: {failure_class}")
    if failure_class in AGENT_FAILURES:
        return "agent_quality"
    if failure_class in RUNTIME_INFRA_FAILURES:
        return "runtime_infrastructure"
    if failure_class in POLICY_OR_PERMISSION_FAILURES:
        return "policy_or_permission"
    if failure_class in EVALUATOR_INFRA_FAILURES:
        return "evaluator_infrastructure"
    if failure_class in FIXTURE_FAILURES:
        return "fixture_invalid"
    return "unavailable_evidence"


def canonical_observation_state(failure_class: str | None, supplied: str | None) -> str:
    if supplied not in {None, "", "observed", "not_observed"}:
        raise AttributionError(f"invalid observation_state: {supplied}")
    if failure_class is None or failure_class in AGENT_FAILURES:
        return supplied or "observed"
    # Infrastructure, fixture, unavailable evidence and pre-execution permission
    # outcomes do not establish the Agent behavior under test.
    return "not_observed"


def quality_denominator_eligible(
    *,
    observation_state: str,
    failure_class: str | None,
) -> bool:
    if observation_state != "observed":
        return False
    if failure_class is None:
        return True
    return failure_class in AGENT_FAILURES


def build_eval_record(
    *,
    eval_id: str,
    run_id: str,
    source_execution_result_ref: str,
    failure_class: str | None,
    observation_state: str | None = None,
    runtime_failure_ref: str | None = None,
    evidence_refs: list[str] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    attribution = classify_failure(failure_class)
    state = canonical_observation_state(failure_class, observation_state)
    eligible = quality_denominator_eligible(
        observation_state=state,
        failure_class=failure_class,
    )
    if not eval_id or not run_id or not source_execution_result_ref:
        raise AttributionError(
            "eval_id, run_id and source_execution_result_ref are required"
        )
    refs = list(
        dict.fromkeys(str(item) for item in (evidence_refs or []) if str(item))
    )
    return {
        "schema_version": "1.1",
        "eval_id": eval_id,
        "run_id": run_id,
        "observation_state": state,
        "failure_class": failure_class,
        "failure_attribution": attribution,
        "quality_denominator_eligible": eligible,
        "runtime_failure_ref": runtime_failure_ref,
        "evidence_refs": refs,
        "reason": reason,
        "source_execution_result_ref": source_execution_result_ref,
    }


def classify_provider_failure(
    provider_failure_class: str | None,
    *,
    observation_state: str,
) -> tuple[str, str | None]:
    """Return provider attribution and existing canonical Eval failure class."""
    if provider_failure_class is None:
        return "none", None
    if provider_failure_class not in PROVIDER_KNOWN_FAILURES:
        raise AttributionError(
            f"unsupported provider failure_class: {provider_failure_class}"
        )
    if provider_failure_class in PROVIDER_OBSERVED_PRODUCT_FAILURES:
        if observation_state != "observed":
            raise AttributionError(
                "observed product failure requires observed structured evidence"
            )
        # Product/compile/test failure was observed. Eval may later compare it to
        # the Golden contract; provider integration must not pre-label it as an
        # Agent regression.
        return "observed_product_failure", None
    if provider_failure_class in PROVIDER_POLICY_FAILURES:
        return "policy_or_permission", "runtime_permission_denied"
    if provider_failure_class == "timeout":
        return "provider_infrastructure", "runtime_timeout"
    if provider_failure_class == "cancelled":
        return "provider_infrastructure", "runtime_cancelled"
    if provider_failure_class in PROVIDER_UNAVAILABLE_EVIDENCE_FAILURES:
        return "unavailable_evidence", "unavailable_required_evidence"
    return "environment_or_provider", "runtime_tool_unavailable"


def build_provider_eval_record(
    *,
    eval_id: str,
    source_execution_result_ref: str,
    evidence: Mapping[str, Any],
    runtime_failure_ref: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Project canonical Tool Runtime Evidence into Eval attribution.

    This function never parses provider logs and never marks provider/environment
    unavailability as Agent behavior regression.
    """
    if evidence.get("schema_version") != "1.1":
        raise AttributionError("provider attribution requires Tool Runtime Evidence v1.1")
    required = {
        "run_id",
        "evidence_id",
        "provider_ref",
        "capability",
        "completion",
        "observation_state",
        "failure_class",
        "environment",
        "safety_strength",
        "evidence_strength",
    }
    missing = sorted(required - set(evidence))
    if missing:
        raise AttributionError(f"Tool Runtime Evidence missing attribution fields: {missing}")

    observation_state = str(evidence["observation_state"])
    if observation_state not in {"observed", "not_observed"}:
        raise AttributionError("invalid Tool Runtime Evidence observation_state")
    provider_failure = evidence.get("failure_class")
    if provider_failure is not None:
        provider_failure = str(provider_failure)
    provider_attribution, canonical_failure = classify_provider_failure(
        provider_failure,
        observation_state=observation_state,
    )

    environment = evidence.get("environment")
    if not isinstance(environment, Mapping):
        raise AttributionError("Tool Runtime Evidence environment must be structured")

    base = build_eval_record(
        eval_id=eval_id,
        run_id=str(evidence["run_id"]),
        source_execution_result_ref=source_execution_result_ref,
        failure_class=canonical_failure,
        observation_state=observation_state,
        runtime_failure_ref=runtime_failure_ref,
        evidence_refs=[str(evidence["evidence_id"])],
        reason=reason,
    )
    base.update(
        {
            "schema_version": "1.2",
            "provider_ref": str(evidence["provider_ref"]),
            "capability": str(evidence["capability"]),
            "completion": str(evidence["completion"]),
            "provider_failure_class": provider_failure,
            "provider_failure_attribution": provider_attribution,
            "environment_profile": environment.get("profile_hint"),
            "safety_strength": int(evidence["safety_strength"]),
            "evidence_strength": int(evidence["evidence_strength"]),
        }
    )
    return base
