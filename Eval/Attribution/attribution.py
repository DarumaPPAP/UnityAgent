"""Canonical Eval failure attribution and quality-denominator policy."""
from __future__ import annotations

from typing import Any

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


def quality_denominator_eligible(*, observation_state: str, failure_class: str | None) -> bool:
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
    eligible = quality_denominator_eligible(observation_state=state, failure_class=failure_class)
    if not eval_id or not run_id or not source_execution_result_ref:
        raise AttributionError("eval_id, run_id and source_execution_result_ref are required")
    refs = list(dict.fromkeys(str(item) for item in (evidence_refs or []) if str(item)))
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
