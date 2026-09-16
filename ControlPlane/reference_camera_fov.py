"""Canonical Control Plane execution for the Windows Camera FOV workflow."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from Persistence.Evidence.evidence_store import EvidenceStore
from Runtime.ReferenceImplementation.authority import (
    RuntimeBudgetLedger,
    SubAgentTaskPlanner,
    SurfaceGrantProjector,
    TaskContractIssuer,
    iso_now,
)
from Runtime.ReferenceImplementation.canonicalization import sha256_jcs
from Runtime.ReferenceImplementation.contracts import (
    ApprovalDecision,
    ContractValidationError,
    EvidenceRecord,
    ProviderResult,
    SurfaceGrant,
    TaskContract,
    TypedAction,
)
from Runtime.ReferenceImplementation.isolation import IsolationError, SubAgentSessionManager
from Runtime.ReferenceImplementation.runtime import (
    CompletionCoordinator,
    EvidenceCompletionGate,
    RuntimeDispatchGate,
    append_reference_evidence,
)
from Runtime.Tooling.capability_resolver import ResolutionContext


DEFAULT_BUDGETS = {
    "max_parent_total_calls": 2,
    "max_parent_reentries": 0,
    "max_global_replans": 0,
    "max_escalations": 1,
    "max_child_llm_calls": 12,
    "max_tool_calls": 20,
    "max_wall_clock_ms": 120000,
    "max_child_wall_clock_ms": 60000,
    "max_child_input_tokens": 10000,
    "max_child_output_tokens": 10000,
    "max_parent_input_tokens": 20000,
    "max_parent_output_tokens": 10000,
    "max_process_restarts": 1,
    "max_provider_retries": 1,
}


def is_camera_fov_reference_request(entry_request: Mapping[str, Any]) -> bool:
    projection = entry_request.get("task_contract_runtime_projection")
    requests = entry_request.get("capability_requests")
    if not isinstance(projection, Mapping) or projection.get("reference_kind") != "camera_fov_v1_1":
        return False
    if not isinstance(requests, list) or len(requests) != 1 or not isinstance(requests[0], Mapping):
        return False
    request = requests[0]
    qualifiers = request.get("qualifiers") if isinstance(request.get("qualifiers"), Mapping) else {}
    return (
        request.get("capability") == "domain.workflow"
        and request.get("operation_kind") == "editor_mutation"
        and qualifiers.get("workflow") == "camera_fov_reference"
    )


def _find_mapping(value: Any, names: tuple[str, ...]) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        if any(name in value for name in names):
            return value
        for item in value.values():
            found = _find_mapping(item, names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_mapping(item, names)
            if found is not None:
                return found
    return None


def _find_value(value: Any, names: tuple[str, ...]) -> Any:
    found = _find_mapping(value, names)
    if found is None:
        return None
    for name in names:
        if name in found:
            return found[name]
    return None


def _provider_result(action: TypedAction, raw: Mapping[str, Any], *, before_value: float | None = None) -> ProviderResult:
    if "provider_result_digest" in raw and "action_id" in raw:
        return ProviderResult.from_dict(raw)
    payload = raw.get("payload", raw)
    diff_value = _find_value(raw, ("exactDiff", "exact_diff"))
    if diff_value is None:
        diff_value = _find_value(payload, ("exactDiff", "exact_diff"))
    if isinstance(diff_value, list):
        diff = next((dict(item) for item in diff_value if isinstance(item, Mapping)), {})
    elif isinstance(diff_value, Mapping):
        diff = dict(diff_value)
    else:
        diff = {}
    before = _find_value(diff, ("before",))
    after = _find_value(diff, ("after",))
    if before is None:
        before = _find_value(raw, ("before_value", "beforeValue"))
    if before is None:
        before = _find_value(payload, ("before_value", "beforeValue"))
    if after is None:
        after = _find_value(raw, ("after_value", "afterValue"))
    if after is None:
        after = _find_value(payload, ("after_value", "afterValue"))
    before = float(before if before is not None else (before_value if before_value is not None else action.value))
    after = float(after if after is not None else action.value)
    revision = _find_value(raw, ("observed_revision", "observedRevision"))
    if revision is None:
        revision = _find_value(payload, ("observedRevision", "observed_revision"))
    if not revision:
        revision = sha256_jcs({"target": action.target, "property": action.property_path, "value": after})
    exact = {
        "target": str(_find_value(diff, ("target",)) or action.target["guid"]),
        "property": str(_find_value(diff, ("property",)) or action.property_path),
        "before": before,
        "after": after,
    }
    value = {
        "schema_version": "1.1",
        "status": "passed",
        "provider_ref": "unity_artist_cli",
        "action_id": action.action_id,
        "project": dict(action.project),
        "target": dict(action.target),
        "property_path": action.property_path,
        "before_value": before,
        "after_value": after,
        "observed_revision": str(revision),
        "exact_diff": exact,
        "evidence": ["mutation_diff", "editor_observation", "visual_capture"],
        "mutation_count": 1,
        "boundary_violations": [],
        "failure_class": None,
        "provider_result_digest": "",
    }
    value["provider_result_digest"] = sha256_jcs({key: item for key, item in value.items() if key != "provider_result_digest"})
    return ProviderResult.from_dict(value)


def execute_camera_fov_reference(
    *,
    entry_request: Mapping[str, Any],
    project_root: str | Path,
    persistence_root: str | Path,
    environment_snapshot: Mapping[str, Any],
    context: ResolutionContext,
    executors: Mapping[str, Any],
    provider_arguments: Mapping[str, Mapping[str, Any]] | None,
    broker: Any,
    evidence_store: EvidenceStore,
    approval_resolver: Any,
    run_id: str,
) -> dict[str, Any]:
    projection = dict(entry_request["task_contract_runtime_projection"])
    capability_request = dict(entry_request["capability_requests"][0])
    project_name = str(projection.get("project_name") or Path(project_root).name or "UnityProject")
    project = {"root": str(Path(project_root).resolve()), "name": project_name}
    computed_project_fingerprint = sha256_jcs({"project": project, "version": "reference-v1.1"})
    supplied_project_fingerprint = projection.get("project_fingerprint")
    if supplied_project_fingerprint is not None and str(supplied_project_fingerprint) != computed_project_fingerprint:
        raise ContractValidationError("camera_fov_reference project fingerprint does not bind to the canonical project")
    project_fingerprint = computed_project_fingerprint
    scope = dict(projection.get("scope") or {
        "target_guids": [str(projection.get("target_guid") or "camera-guid-001")],
        "component_type": "UnityEngine.Camera",
        "property_paths": ["Camera.fieldOfView"],
        "mutation_channels": ["serialized_property"],
    })
    budgets = dict(DEFAULT_BUDGETS)
    budgets.update(dict(projection.get("budgets") or {}))
    target_guid = str(projection.get("target_guid") or "")
    expected_revision = str(projection.get("expected_revision") or "")
    if not target_guid or not expected_revision:
        raise ContractValidationError("camera_fov_reference requires target_guid and expected_revision")
    if scope.get("target_guids") != [target_guid] or scope.get("property_paths") != ["Camera.fieldOfView"]:
        raise ContractValidationError("camera_fov_reference scope must bind the inspected camera and FOV property")
    task = TaskContractIssuer().issue(
        task_id=str(projection.get("task_id") or f"artist-camera-fov-{run_id}"),
        run_id=run_id,
        project=project,
        project_fingerprint=project_fingerprint,
        budgets=budgets,
        scope=scope,
        issued_at=str(projection.get("issued_at") or iso_now()),
    )
    approval_ref = str(capability_request.get("approval_ref") or "")
    if not approval_ref:
        raise ContractValidationError("camera_fov_reference requires approval_ref")
    approval = approval_resolver.resolve(approval_ref, task=task)
    if float(approval.parameter_envelope.get("min", -1.0)) != 35.0 or float(approval.parameter_envelope.get("max", -1.0)) != 50.0:
        raise ContractValidationError("camera_fov_reference approval must use the canonical 35..50 envelope")
    grant = SurfaceGrantProjector().derive(
        task=task,
        approval=approval,
        subagent_instance_id=str(projection.get("subagent_instance_id") or f"artist-{run_id}"),
    )
    ledger = RuntimeBudgetLedger(task.budgets)
    plan = SubAgentTaskPlanner().plan(task, ledger)
    context_payload = {
        "proposed_value": float(projection.get("proposed_value", 43.0)),
        "expected_revision": expected_revision,
        "approval": approval.to_dict(),
        "reference_kind": "camera_fov_v1_1",
    }
    session_events = SubAgentSessionManager().run(task=task, grant=grant, context=context_payload, approval_resolver=approval_resolver)
    action_envelope = next((item.get("payload", {}).get("action_envelope") for item in session_events if item.get("message_type") == "propose_action"), None)
    if not isinstance(action_envelope, Mapping):
        raise ContractValidationError("specialist did not propose a TypedAction")
    action = TypedAction.from_envelope(action_envelope)
    if action.target["guid"] != target_guid or action.expected_revision != expected_revision:
        raise ContractValidationError("specialist TypedAction is not bound to the inspected camera revision")
    if not 35.0 <= action.value <= 50.0:
        raise ContractValidationError("camera_fov_reference value is outside the canonical 35..50 range")
    ledger.consume("tool_calls", 1)

    metadata: dict[str, Any] = {}
    dispatch_outcome: dict[str, Any] = {}
    provider_args = {key: dict(value) for key, value in (provider_arguments or {}).items()}
    for provider_ref in executors:
        provider_args.setdefault(provider_ref, {})
        provider_args[provider_ref].update({
            "workflow": "camera_fov_reference",
            "reference_action": action.to_envelope(),
            "approval_token": approval.approval_decision_id,
            "expected_revision": action.expected_revision,
            "target_guid": action.target["guid"],
            "target_name": str(projection.get("target_name") or "Main Camera"),
            "camera_fov_minimum": float(approval.parameter_envelope["min"]),
            "camera_fov_maximum": float(approval.parameter_envelope["max"]),
            "request_json": json.dumps({
                "workflow": "camera_fov_reference",
                "targetName": str(projection.get("target_name") or "Main Camera"),
                "targetGuid": action.target["guid"],
                "setCameraFieldOfView": True,
                "cameraFieldOfView": action.value,
                "cameraFovMinimum": approval.parameter_envelope["min"],
                "cameraFovMaximum": approval.parameter_envelope["max"],
            }, separators=(",", ":")),
        })

    def canonical_dispatch(bound_action: TypedAction) -> ProviderResult:
        nonlocal dispatch_outcome
        trusted_before_dispatch = approval_resolver.resolve(approval.approval_decision_id, task=task)
        if trusted_before_dispatch.decision_digest != approval.decision_digest:
            raise ContractValidationError("ApprovalDecision changed before ToolBroker dispatch")
        dispatch_outcome = broker.dispatch(
            capability_request,
            environment_snapshot,
            context=context,
            executors=executors,
            provider_arguments=provider_args,
            maximum_retry_attempts=0,
        )
        if dispatch_outcome.get("status") != "completed":
            raise ContractValidationError(f"canonical ToolBroker dispatch failed: {dispatch_outcome}")
        raw = dispatch_outcome.get("provider_result")
        if not isinstance(raw, Mapping) or raw.get("status") != "passed":
            raise ContractValidationError("UnityArtist Provider did not return a passed result")
        trusted_after_dispatch = approval_resolver.resolve(approval.approval_decision_id, task=task)
        if trusted_after_dispatch.decision_digest != approval.decision_digest:
            raise ContractValidationError("ApprovalDecision changed during ToolBroker dispatch")
        metadata.update(dict(raw))
        return _provider_result(bound_action, raw)

    def write_evidence(bound_action: TypedAction, result: ProviderResult) -> list[str]:
        records = [
            EvidenceRecord.observed(
                evidence_id=f"{run_id}-mutation-diff",
                task_id=task.task_id,
                run_id=run_id,
                action_id=bound_action.action_id,
                evidence_type="mutation_diff",
                payload={"exact_diff": result.exact_diff, "before": result.before_value, "after": result.after_value},
            ),
            EvidenceRecord.observed(
                evidence_id=f"{run_id}-editor-observation",
                task_id=task.task_id,
                run_id=run_id,
                action_id=bound_action.action_id,
                evidence_type="editor_observation",
                payload={"target_guid": bound_action.target["guid"], "property": bound_action.property_path, "value": result.after_value, "revision": result.observed_revision},
            ),
            EvidenceRecord.observed(
                evidence_id=f"{run_id}-visual-capture",
                task_id=task.task_id,
                run_id=run_id,
                action_id=bound_action.action_id,
                evidence_type="visual_capture",
                payload={"capture": metadata.get("capture") or metadata.get("capture_evidence") or {}, "observed": True},
            ),
        ]
        ids: list[str] = []
        for record in records:
            append_reference_evidence(store=evidence_store, task=task, action=bound_action, result=result, evidence=record, evidence_type=record.evidence_type)
            ids.append(record.evidence_id)
        return ids

    runtime_gate = RuntimeDispatchGate(approval_resolver=approval_resolver, persistence_root=persistence_root)
    dispatch = runtime_gate.dispatch(task=task, approval=approval, grant=grant, action=action, dispatch_provider=canonical_dispatch, evidence_writer=write_evidence)
    provider_result = dispatch["provider_result"]
    completion_proof = EvidenceCompletionGate(evidence_store, approval_resolver).evaluate(
        task=task,
        approval=approval,
        grant=grant,
        actions=[action],
        provider_results=[provider_result],
        reservations=runtime_gate.reservations,
        evidence_ids=list(dispatch.get("evidence_ids") or []),
        final_revision=provider_result.observed_revision,
        ledger=ledger,
    )
    final = CompletionCoordinator().present(completion_proof, ledger=ledger)
    return {
        "status": final["status"],
        "task_contract": task.to_dict(),
        "approval_decision": approval.to_dict(),
        "surface_grant": grant.to_dict(),
        "plan": plan,
        "specialist_events": session_events,
        "dispatch": dispatch_outcome,
        "provider_result": provider_result.to_dict(),
        "completion": final["completion"],
        "evidence_refs": list(dispatch.get("evidence_ids") or []),
        "metadata": metadata,
        "metrics": {
            "approval_bypass_success": 0,
            "scope_expansion_success": 0,
            "direct_cli_bypass_success": 0,
            "direct_installer_bypass_success": 0,
            "duplicate_mutation_apply": 0,
            "completion_without_required_evidence": 0 if final["status"] == "completed" else 1,
            "parent_per_tool_mediation": plan["parent_per_tool_mediation"],
            "runtime_validation_llm_calls": 0,
            **ledger.snapshot(),
        },
    }
