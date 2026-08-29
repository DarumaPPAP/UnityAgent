"""Native Runtime -> Eval adapter with no execution or lossy fact reconstruction."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from Eval.Attribution.attribution import build_eval_record


class RuntimeEvalAdapterError(ValueError):
    pass


def adapt_execution_result(
    execution_result: dict[str, Any],
    *,
    eval_id: str,
    source_execution_result_ref: str,
    expect_mutation: bool = False,
) -> dict[str, Any]:
    """Project canonical Runtime facts into Eval without invoking Runtime.

    `changed_paths` is copied structurally. Textual patch artifacts are never
    parsed to recreate the fact. Mutation no-op classification is evaluator-side
    and is applied only when the caller declares that the Golden case expects a
    mutation.
    """
    if execution_result.get("schema_version") != "1.0":
        raise RuntimeEvalAdapterError("unsupported ExecutionResult schema_version")
    run_id = str(execution_result.get("run_id") or "")
    if not run_id:
        raise RuntimeEvalAdapterError("ExecutionResult.run_id is required")
    changed = execution_result.get("changed_paths")
    if not isinstance(changed, dict) or changed.get("observation_state") not in {"observed", "not_observed"}:
        raise RuntimeEvalAdapterError("ExecutionResult.changed_paths is incomplete")
    paths = changed.get("paths")
    if not isinstance(paths, list) or any(not isinstance(item, str) or not item for item in paths):
        raise RuntimeEvalAdapterError("ExecutionResult.changed_paths.paths must be a string array")

    runtime_failure = execution_result.get("runtime_failure")
    failure_class = None
    runtime_failure_ref = None
    reason = ""
    supplied_observation = "observed"
    if runtime_failure is not None:
        if not isinstance(runtime_failure, dict):
            raise RuntimeEvalAdapterError("runtime_failure must be an object or null")
        failure_class = str(runtime_failure.get("failure_class") or "") or None
        reason = str(runtime_failure.get("reason") or "")
        supplied_observation = str(runtime_failure.get("observation_state") or "not_observed")
        runtime_failure_ref = f"{run_id}:runtime-failure"
    elif expect_mutation and changed.get("observation_state") == "observed" and not paths:
        failure_class = "agent_behavior_regression"
        reason = "expected mutation produced an observed empty changed_paths set"

    eval_record = build_eval_record(
        eval_id=eval_id,
        run_id=run_id,
        source_execution_result_ref=source_execution_result_ref,
        failure_class=failure_class,
        observation_state=supplied_observation,
        runtime_failure_ref=runtime_failure_ref,
        evidence_refs=list(execution_result.get("evidence_refs") or []),
        reason=reason,
    )
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": execution_result.get("status"),
        "changed_paths": deepcopy(changed),
        "gate_outcomes": deepcopy(execution_result.get("gate_outcomes") or []),
        "tool_identity": deepcopy(execution_result.get("tool_identity") or {}),
        "definition_fingerprint": deepcopy(execution_result.get("definition_fingerprint") or {}),
        "eval_record": eval_record,
    }
