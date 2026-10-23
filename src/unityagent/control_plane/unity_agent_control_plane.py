"""Thin UnityAgent Control Plane over the existing Runtime chain.

This module is the only Entry-facing execution facade. It owns run identity and
durable execution/workflow state, asks Orchestration for a provider-independent
handoff, and sends capabilities to the existing ToolBroker. Semantic Local Loop
decisions are owned by src/unityagent/orchestration/loop and are never inferred from unityagent.runtime
capability iteration here.
"""
from __future__ import annotations
from unityagent.control_plane.measurement import measured, measured_call, capture_persistence
from unityagent.resources import resource_root

from datetime import datetime, timezone
import uuid
import time
from copy import deepcopy
from functools import wraps
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator, ValidationError

from unityagent.orchestration.orchestrator.orchestrator import runtime_handoff, runtime_node_for_requests
from unityagent.orchestration.routing.adaptive_execution import select_execution_path, observe_execution_strategy
from unityagent.orchestration.routing.route_selector import load_routes, resolve_specialist, select_route, select_specialist_capability, task_fingerprint_from_intent
from unityagent.orchestration.tool_routing.capability_request_builder import (build_capability_requests, build_specialist_capability_requests, conditions_for_intent,
    mutation_scope_for_intent, task_contract_projection)
from unityagent.context.manifest.build_context_manifest import build as build_context_manifest
from unityagent.context.selection.project_context_inputs import derive_context_inputs
from unityagent.context.selection.specialist_context import observation_items
from unityagent.orchestration.graph.state_mapping import workflow_state_patch
from unityagent.orchestration.loop.state_mapping import loop_control_state_patch
from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.evidence.evidence_store import EvidenceStore
from unityagent.persistence.evidence.runtime_adapter import append_runtime_execution_evidence
from unityagent.persistence.install.receipt_store import InstallReceiptStore
from unityagent.persistence.state.state_store import StateStore
from unityagent.persistence.store.atomic_store import PersistenceError, read_json, relative_ref, sha256_json, write_immutable_json
from unityagent.persistence.contracts.definition_fingerprint import validate_definition_fingerprint
from unityagent.runtime.contracts.install_receipt_contract import validate_install_receipt
from unityagent.runtime.evidence_capture.tool_runtime_evidence import normalize_provider_result, observation_payload
from unityagent.runtime.evidence_capture.toolchain_evidence import normalize_toolchain_result
from unityagent.runtime.tooling.environment.environment_snapshot import EnvironmentSnapshot
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.provider_registry import RuntimeProviderRegistry
from unityagent.runtime.tooling.tool_broker import ToolBroker
from unityagent.runtime.contracts.capability_contract import validate_capability_request
from unityagent.runtime.contracts.runtime_handoff import validate_runtime_handoff
from unityagent.runtime.contracts.reasoning_output import ReasoningOutputError, verify_reasoning_artifact
from unityagent.runtime.contracts.toolchain_setup_contract import validate_toolchain_setup_request
from unityagent.runtime.reference_implementation.authority import ApprovalDecisionResolver
from unityagent.runtime.handoff.reasoning_runtime import ContextBindingError, execute_reasoning
from unityagent.runtime.runner.codex.codex_runner import CodexRunnerError
from unityagent.control_plane.reference_camera_fov import execute_camera_fov_reference, is_camera_fov_reference_request

from unityagent.runtime.guardrails.project_lease import ProjectLeaseBusy, acquire_project_lease

ROOT = resource_root()
ENTRY_SCHEMA_PATH = Path("src/unityagent/runtime/contracts/entry-request.schema.yaml")
ENTRY_V2_SCHEMA_PATH = Path("src/unityagent/runtime/contracts/entry-request.v2.schema.yaml")
PROVIDER_ID_KEYS = frozenset({"provider", "provider_ref", "provider_id"})
ENTRY_AUTHORITY_KEYS = frozenset({"route_id", "capability_requests", "context_id", "context_fingerprint",
    "node_id", "execution_profile", "task_contract_runtime_projection", "mutation_scope", "validation_requirements",
    "task_fingerprint", "intent", "artifact", "scope", "failure_mode", "architecture_state",
    "mutation_target", "evidence_state", "project_access", "execution_mode", "provider_resolution", "runtime_action", "output_contract_ref"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _contains_provider_identity(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(key) in PROVIDER_ID_KEYS for key in value) or any(
            _contains_provider_identity(item) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_provider_identity(item) for item in value)
    return False


def validate_entry_request(value: dict[str, Any], *, root: Path = ROOT) -> None:
    """Validate an Entry request and enforce the no-direct-Provider boundary."""
    schema_path = ENTRY_V2_SCHEMA_PATH if value.get("schema_version") == "2.0" else ENTRY_SCHEMA_PATH
    schema = yaml.safe_load((root / schema_path).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
    if _contains_provider_identity(value):
        raise ValueError("Entry request must not contain Provider identity")
    if value["schema_version"] == "2.0":
        if any(key in value["intent"] for key in ENTRY_AUTHORITY_KEYS):
            raise ValueError("Entry intent must not contain Orchestration or Context authority fields")
        if value['intent']['kind'] == 'csharp_local_fix':
            from unityagent.runtime.sandbox.workspace_guard import normalize_relative_path
            path = value['intent']['target_source']
            if normalize_relative_path(path) != path or not path.startswith('Assets/') or not path.endswith('.cs'):
                raise ValueError('C# target must be one canonical source path under Assets')
    else:
        for request in value["capability_requests"]:
            validate_capability_request(dict(request), root=root)
            if str(request["project_root"]).casefold() != str(value["project_root"]).casefold():
                raise ValueError("CapabilityRequest project_root must match Entry project_root")


def _project_exclusive(operation):
    """Control Plane間の競合をRuntimeへ渡す前に検出し、Evidence保存まで保持する。"""
    @wraps(operation)
    def execute(plane, entry_request, **parameters):
        validate_entry_request(entry_request)
        if entry_request['schema_version'] == '1.0':
            raise ValueError('Entry v1 migration required: use v2 without caller-supplied Context identity')
        owner = parameters.get('run_id') or _new_run_id(str(entry_request['request_id']))
        try:
            task_fingerprint_from_intent(dict(entry_request['intent']),
                _snapshot_dict(parameters['environment_snapshot']),
                project_root=str(entry_request['project_root']),
                policy_allowed=parameters['context'].policy_allowed)
        except ValueError as exc:
            return {'schema_version': '2.0', 'status': 'blocked', 'run_id': owner,
                    'reason': str(exc), 'results': [], 'evidence_refs': []}
        stack = ExitStack()
        with stack:
            try:
                with measured(plane, owner, 'lease'):
                    stack.enter_context(acquire_project_lease(entry_request['project_root'], owner=owner))
                claims = parameters.pop('_host_resource_claims', ())
                if claims:
                    from unityagent.runtime.guardrails.project_lease import acquire_host_claims
                    with measured(plane, owner, 'lease'):
                        stack.enter_context(acquire_host_claims(claims, owner=owner))
            except ProjectLeaseBusy as exc:
                return {'schema_version': '2.0', 'status': 'blocked', 'run_id': owner,
                        'failure_class': 'resource_busy', 'reason': str(exc),
                        'results': [], 'evidence_refs': []}
            except (OSError, ValueError) as exc:
                return {'schema_version': '2.0', 'status': 'blocked', 'run_id': owner,
                        'failure_class': 'resource_unavailable', 'reason': str(exc),
                        'results': [], 'evidence_refs': []}
            with capture_persistence(plane, owner):
                return operation(plane, entry_request, **{**parameters, 'run_id': owner})
    return execute


def _snapshot_dict(snapshot: EnvironmentSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    value = snapshot.to_dict() if hasattr(snapshot, "to_dict") else dict(snapshot)
    if not isinstance(value, dict):
        raise ValueError("Environment Snapshot must be a mapping")
    return value


def _new_run_id(request_id: str) -> str:
    return f"run-{request_id}-{uuid.uuid4().hex[:12]}"


class UnityAgentControlPlane:
    """UnityAgent's single run-owning facade for UI and Codex Entry layers."""

    def __init__(
        self,
        persistence_root: str | Path,
        *,
        broker: ToolBroker | None = None,
        state_store: StateStore | None = None,
        evidence_store: EvidenceStore | None = None,
        receipt_store: InstallReceiptStore | None = None,
        approval_resolver: ApprovalDecisionResolver | None = None,
    ) -> None:
        self.broker = broker or ToolBroker()
        self.state_store = state_store or StateStore(persistence_root)
        self.evidence_store = evidence_store or EvidenceStore(persistence_root)
        self.receipt_store = receipt_store or InstallReceiptStore(persistence_root)
        self.approval_resolver = approval_resolver or ApprovalDecisionResolver(ApprovalDecisionStore(persistence_root))

    def _blocked_before_dispatch(
        self, *, run_id: str, entry_point: str, definition_fingerprint: Mapping[str, Any],
        stage: str, error: Exception, started_at: float,
    ) -> dict[str, Any]:
        """Persist pre-provider failure as an observed failure, not a provider result."""
        elapsed_ms = round((time.monotonic() - started_at) * 1000, 3)
        reason = str(error)
        failure_class = "precondition_failed"
        payload = {
            "schema_version": "1.0", "run_id": run_id, "status": "blocked",
            "failure_stage": stage, "failure_class": failure_class,
            "error_type": type(error).__name__, "reason": reason, "elapsed_ms": elapsed_ms,
            "provider_executed": False,
        }
        digest = sha256_json(payload)
        path = self.evidence_store.layout.snapshot(run_id, "preflight-failure", digest)
        write_immutable_json(path, payload)
        payload_ref = relative_ref(self.evidence_store.layout.root, path)
        evidence_id = f"{run_id}-preflight-evidence-1"
        self.evidence_store.append({
            "schema_version": "1.1", "evidence_id": evidence_id, "run_id": run_id,
            "step_id": stage, "source_type": "preflight_failure",
            "source_ref": "unityagent.control_plane.preflight",
            "timestamp": _now(), "hash": digest, "producer": "unityagent.control_plane",
            "verification_status": "failed", "provenance": [f"control_plane:{stage}"],
            "payload_ref": payload_ref, "definition_fingerprint": dict(definition_fingerprint),
            "failure_class": failure_class, "failure_stage": stage, "latency_ms": elapsed_ms,
        })
        self.evidence_store.verify_record(evidence_id, expected_run_id=run_id)
        state_ref = self._save_execution_state(
            run_id=run_id, step_id=stage, action_id="preflight",
            status="blocked", evidence_refs=[evidence_id],
        )
        return {
            "schema_version": "2.0", "status": "blocked", "run_id": run_id,
            "entry_point": entry_point,
            "layer_trace": ["entry", "control_plane", "preflight", "evidence_state"],
            "failure_stage": stage, "failure_class": failure_class, "reason": reason,
            "elapsed_ms": elapsed_ms, "results": [], "evidence_refs": [evidence_id],
            "state_ref": state_ref, "provider_executed": False,
        }

    def _save_execution_state(
        self,
        *,
        run_id: str,
        step_id: str,
        action_id: str,
        status: str,
        evidence_refs: list[str],
    ) -> str:
        return self.state_store.save_execution_state(
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "status": status,
                "current_step_id": step_id,
                "current_action_id": action_id,
                "evidence_refs": list(dict.fromkeys(evidence_refs)),
                "updated_at": _now(),
            }
        )

    def _save_workflow_state(
        self,
        *,
        run_id: str,
        route_id: str,
        node_id: str,
        evidence_refs: list[str],
    ) -> str:
        return self.state_store.save_workflow_state(
            workflow_state_patch(
                run_id=run_id,
                parent_graph_id="development",
                active_subgraph_id=route_id,
                active_node_id=node_id,
                shared_state_refs=list(dict.fromkeys(evidence_refs)),
            )
        )

    def _save_loop_state(
        self,
        *,
        run_id: str,
        loop_id: str,
        attempt: int,
        decision: str,
        progress_marker: str | None,
    ) -> str:
        return self.state_store.save_loop_control_state(
            loop_control_state_patch(
                run_id=run_id,
                loop_id=loop_id,
                semantic_attempt=attempt,
                progress_marker=progress_marker,
                decision=decision,
            )
        )

    def _observe_strategy(self, result, *, current_path=None, observation_run_id=None, task_id=None, attempt=None, gates=None):
        """結果確定後の補助記録。保存失敗で実行済みProviderを再送しない。"""
        run_id = observation_run_id or result['run_id']
        refs = []
        diagnostics = []
        try:
            if current_path is None and result.get('orchestration_decision_ref'):
                proof = read_json(self.state_store.layout.root / result['orchestration_decision_ref'])
                current_path = proof['execution_plan']['path']
            failures = [item.get('provider_result') or item.get('runtime_failure') or item for item in result.get('results', [])]
            known_failures = {'execution_failed', 'approval_required', 'approval_denied', 'scope_denied',
                'permission_denied', 'runtime_permission_denied', 'environment_unavailable', 'resource_busy',
                'resource_conflict', 'resource_unavailable', 'context_insufficient', 'runtime_tool_unavailable',
                'runtime_timeout', 'runtime_protocol_failure', 'runtime_cancelled',
                'unavailable', 'unknown', 'unhealthy', 'ambiguous_binding', 'blocked_by_policy',
                'blocked_by_approval', 'scope_violation', 'unsupported', 'backend_not_implemented',
                'precondition_failed', 'cancelled', 'timeout', 'observed_test_failure', 'not_observed',
                'runner_unavailable', 'structured_output_invalid', 'context_binding_failed',
                'world_plan_contract_failed', 'mutation_attempt_detected', 'unavailable_required_evidence', 'task_fixture_invalid'}
            raw_failure = result.get('failure_class') or next((f.get('failure_class') for f in failures if f.get('failure_class')), None)
            failure = raw_failure if raw_failure in known_failures else 'unclassified_failure' if raw_failure else None
            uncertain = any(f.get('uncertain_side_effects') is True for f in failures)
            # 初期選択のFactは残作業のFactではない。未観測の再計画要否を作らない。
            inputs = dict(selection_inputs={}, failure_class=failure, uncertain_side_effects=uncertain)
            proposal = observe_execution_strategy(current_path=current_path, **inputs)
            record = {**proposal, **inputs, 'schema_version': '1.0', 'run_id': run_id,
                'result_run_id': result['run_id'], 'step_id': result.get('handoff', {}).get('step_id', 'task-acceptance'),
                'definition_fingerprint': dict(result.get('handoff', {})['definition_fingerprint']),
                'input_digest': sha256_json({'current_path': current_path, **inputs}),
                'evidence_refs': list(dict.fromkeys(result.get('evidence_refs', []))),
                'result_status': result['status'], 'gates': dict(gates or {}),
                'context_manifest_ref': result.get('context_manifest_ref'),
                'orchestration_decision_ref': result.get('orchestration_decision_ref')}
            if task_id is not None:
                record.update(task_id=task_id, attempt=attempt)
            schema = yaml.safe_load((ROOT / 'src/unityagent/orchestration/contracts/strategy-observation.schema.yaml').read_text(encoding='utf-8'))
            Draft202012Validator(schema).validate(record)
            path = self.state_store.layout.snapshot(run_id, 'strategy-observation', sha256_json(record))
            write_immutable_json(path, record)
            refs.append(relative_ref(self.state_store.layout.root, path))
        except (OSError, PersistenceError, ValueError, KeyError, TypeError, ValidationError) as exc:
            # 生の例外には引数等が含まれ得るため、補助診断は固定分類だけを保存する。
            diagnostics.append({'code': 'observation_persistence_failed', 'error_type': type(exc).__name__})
        additions = {'strategy_observation_refs': refs}
        if diagnostics:
            additions['strategy_observation_diagnostics'] = diagnostics
        if observation_run_id is None:
            try:
                state = self.state_store.load_execution_state(result['run_id'])
                self.state_store.save_execution_state({**state, **additions,
                    'definition_fingerprint': dict(result['handoff']['definition_fingerprint']),
                    'context_manifest_ref': result.get('context_manifest_ref'),
                    'orchestration_decision_ref': result.get('orchestration_decision_ref')})
            except (OSError, PersistenceError, ValueError) as exc:
                # snapshotがあっても参照の保存失敗は完全な観測とは扱わない。
                additions.setdefault('strategy_observation_diagnostics', []).append(
                    {'code': 'observation_reference_persistence_failed', 'error_type': type(exc).__name__})
        return {**result, **additions}

    @_project_exclusive
    def execute(
        self,
        entry_request: dict[str, Any],
        *,
        environment_snapshot: EnvironmentSnapshot | Mapping[str, Any],
        context: ResolutionContext,
        executors: Mapping[str, Any],
        definition_fingerprint: Mapping[str, Any],
        provider_arguments: Mapping[str, Mapping[str, Any]] | None = None,
        run_id: str | None = None,
        specialist_pilot_enabled: bool = False,
        reasoning_model: str | None = None,
        reasoning_model_revision: str | None = None,
        reasoning_effort: str = "high",
        reasoning_timeout_seconds: float = 120.0,
        reasoning_command_prefix: list[str] | None = None,
        maximum_retry_attempts: int = 1,
        cancel_event=None,
        _execution_deadline=None,
        _workspace_dispatch_token=None,
        _strategy_consumer=None,
    ) -> dict[str, Any]:
        """Run Entry and Orchestration through the selected runtime handoff, then record Evidence."""
        validate_entry_request(entry_request)
        if entry_request["schema_version"] == "1.0":
            raise ValueError("Entry v1 migration required: use v2 without caller-supplied Context identity")
        validate_definition_fingerprint(dict(definition_fingerprint))
        snapshot = _snapshot_dict(environment_snapshot)
        resolved_run_id = run_id or _new_run_id(str(entry_request["request_id"]))
        preflight_started_at = time.monotonic()
        intent = dict(entry_request["intent"])
        try:
            task_fingerprint = task_fingerprint_from_intent(intent, snapshot,
                project_root=str(entry_request["project_root"]), policy_allowed=context.policy_allowed)
            route_catalog = load_routes(ROOT / "src/unityagent/orchestration/routing/task-routes.yaml")
            route_decision = select_route(task_fingerprint, route_catalog)
            route_id = str(route_decision["route_id"])
            assigned_subagent = route_catalog['routes'][route_id].get('specialist_profile')
            from unityagent.orchestration.routing.subagent_identity import canonical_subagent_id
            requested_subagent = canonical_subagent_id(entry_request.get('requested_subagent'))
            if requested_subagent is not None and requested_subagent != assigned_subagent:
                raise ValueError('requested SubAgent is incompatible with resolved task ownership')
            conditions = conditions_for_intent(intent, task_fingerprint)
            mutation_scope = mutation_scope_for_intent(intent, task_fingerprint)
            capability_requests = build_capability_requests(route_id=route_id,
                project_root=str(entry_request["project_root"]), active_conditions=conditions,
                mutation_scope=mutation_scope, approval_ref=entry_request.get("approval_ref"))
            specialist_requests = build_specialist_capability_requests(route_id, str(entry_request["project_root"]), active_conditions=conditions)
            selected_capability = select_specialist_capability(route_id, capability_requests + specialist_requests)
            if not capability_requests:
                raise ValueError(f"Orchestration produced no runnable CapabilityRequest: {route_id}")
            mutating_requests = [request for request in capability_requests if request["operation_kind"] != "read"]
            if mutating_requests:
                if not mutation_scope:
                    raise ValueError("v2 Entry has no approved mutation scope projection for this route")
                if not entry_request.get("approval_ref"):
                    raise ValueError("v2 mutation requires an approval_ref bound to the projected scope")
                if any(request.get("mutation_scope") != mutation_scope for request in mutating_requests):
                    raise ValueError("Orchestration mutation scope projection does not match generated CapabilityRequest")
            required_capability = "visual.capture" if intent["kind"] == "visual_capture" else (
                "project.inspect" if intent["kind"] == "project_inspection" else None)
            if required_capability and required_capability not in {item["capability"] for item in capability_requests}:
                raise ValueError(f"selected route does not support requested outcome: {required_capability}")
            for request in capability_requests:
                validate_capability_request(request)
            projection = task_contract_projection(route_id, active_conditions=conditions)
            requirements = list(dict.fromkeys(evidence for request in capability_requests
                for evidence in request["required_evidence"]))
            capabilities = [str(request["capability"]) for request in capability_requests]
        except ValueError as exc:
            return self._blocked_before_dispatch(
                run_id=resolved_run_id, entry_point=str(entry_request["entry_point"]),
                definition_fingerprint=definition_fingerprint, stage="routing",
                error=exc, started_at=preflight_started_at)
        try:
            inputs = measured_call(self, resolved_run_id, 'preparation', derive_context_inputs, str(entry_request["project_root"]), snapshot, intent)
        except ValueError as exc:
            return self._blocked_before_dispatch(
                run_id=resolved_run_id, entry_point=str(entry_request["entry_point"]),
                definition_fingerprint=definition_fingerprint, stage="preparation",
                error=exc, started_at=preflight_started_at)
        specialist_selection = resolve_specialist(route_id, selected_capability or capabilities[0], snapshot, pilot_enabled=specialist_pilot_enabled, context_items=inputs["specialist_items"], activation_only=True)
        if specialist_selection["status"] in {"unavailable", "unsupported"}:
            return {"schema_version": "2.0", "status": "blocked", "run_id": resolved_run_id,
                    "reason": f"Specialist {specialist_selection['status']}: {selected_capability}", "results": [], "evidence_refs": []}
        project_path = Path(entry_request["project_root"]).resolve()
        persistence_roots = (self.state_store.layout.root, self.evidence_store.layout.root)
        if specialist_selection.get("provider_resolution") == "not_required" and any(root == project_path or project_path in root.parents for root in persistence_roots):
            return {"schema_version": "2.0", "status": "blocked", "run_id": resolved_run_id, "reason": "reasoning Persistence root must be outside the original Project", "results": [], "evidence_refs": []}
        try:
            manifest = measured_call(self, resolved_run_id, 'context', build_context_manifest, resolved_run_id, route_id, project_facts=inputs["project_facts"],
                bindings=inputs["bindings"], capability_ids=capabilities, active_conditions=conditions,
                specialist_selection=specialist_selection if specialist_selection["status"] != "activated" else None,
                specialist_items=inputs["specialist_items"] if specialist_selection["status"] == "selected" else None,
                specialist_tags=inputs["specialist_tags"] if specialist_selection["status"] == "selected" else None,
                required_specialist_keys=inputs["required_specialist_keys"] if specialist_selection["status"] == "selected" else None)
        except (ValueError, FileNotFoundError) as exc:
            return self._blocked_before_dispatch(
                run_id=resolved_run_id, entry_point=str(entry_request["entry_point"]),
                definition_fingerprint=definition_fingerprint, stage="context",
                error=exc, started_at=preflight_started_at)
        view = manifest["materialized_context"]
        manifest_path = self.state_store.layout.snapshot(resolved_run_id, "context-manifest", sha256_json(manifest))
        write_immutable_json(manifest_path, manifest)
        manifest_ref = relative_ref(self.state_store.layout.root, manifest_path)
        if manifest["budget_report"]["decision"] != "within_budget" or view["unresolved_bindings"]:
            return {"schema_version": "2.0", "status": "blocked", "run_id": resolved_run_id,
                    "reason": f"Context gate: {manifest['budget_report']['decision']}; unresolved={view['unresolved_bindings']}",
                    "context_manifest_ref": manifest_ref, "results": [], "evidence_refs": []}
        # 経路は調整コストの判断。権限とContextのGateは上で検証済みのまま維持する。
        bounded_inspection = intent['kind'] == 'project_inspection'
        risk = {'R0': 'low', 'R1': 'medium', 'R2': 'high', 'R3': 'critical'}.get(
            projection['risk_level'], 'critical')
        selection_inputs = dict(
            task_count=1, simple_task=bounded_inspection, risk=risk,
            design_review='not_required' if bounded_inspection else route_decision['design_review'],
            requires_replan=False, project_bound=task_fingerprint['project_access'] == 'authorized',
            scope_known=True, requested_subagent=requested_subagent,
            required_subagents=(assigned_subagent,) if assigned_subagent else (),
            context_profile=manifest['budget_report']['profile'], resource_conflict=False)
        execution_plan = select_execution_path(**selection_inputs)
        if execution_plan['status'] == 'blocked':
            return {'schema_version': '2.0', 'status': 'blocked', 'run_id': resolved_run_id,
                    'reason': execution_plan['reason'], 'results': [], 'evidence_refs': []}
        node_id = 'inspect_sources' if execution_plan['path'] == 'fast' else runtime_node_for_requests(
            capability_requests,
            graph_path=ROOT / 'src/unityagent/orchestration/definitions/development-parent-graph.yaml')
        effective_request = {**entry_request, "route_id": route_id, "node_id": node_id,
            "execution_profile": route_decision["profile"], "task_contract_runtime_projection": projection,
            "mutation_scope": mutation_scope, "validation_requirements": requirements,
            "capability_requests": capability_requests, "context_id": view["context_id"],
            "context_fingerprint": view["context_fingerprint"]["value"]}
        definition_fingerprint = {**definition_fingerprint,
            "policy_revision": view["definition_fingerprint"]["policy_revision"],
            "context_revision": view["definition_fingerprint"]["context_revision"]}
        runtime_action = {"kind": "capability_dispatch"}
        reasoning_action = None
        if specialist_selection["status"] in {"selected", "activated"} and specialist_selection.get("provider_resolution") == "not_required":
            reasoning_action = {"kind": "specialist_reasoning", **{key: specialist_selection[key] for key in ("profile_id", "capability", "execution_mode", "provider_resolution", "output_contract_ref", "instructions_ref")}}
            if specialist_selection["status"] == "selected":
                runtime_action = reasoning_action
                route_decision["profile"] = "generic_planning"
                effective_request["execution_profile"] = "generic_planning"
        handoff = runtime_handoff(
            run_id=resolved_run_id,
            node_id=node_id,
            route_id=route_id,
            execution_profile=str(route_decision["profile"]),
            context_id=view["context_id"],
            context_fingerprint=view["context_fingerprint"]["value"],
            task_contract_runtime_projection=projection,
            mutation_scope=mutation_scope,
            validation_requirements=requirements,
            capability_requests=capability_requests,
            runtime_action=runtime_action,
            definition_fingerprint=dict(definition_fingerprint),
        )
        validate_runtime_handoff(handoff)
        routing_proof = {"execution_plan": execution_plan,
            "task_fingerprint": task_fingerprint, "route_decision": route_decision,
            "active_conditions": sorted(conditions), "task_contract_projection": projection,
            "capability_requests": handoff["capability_requests"], "specialist_capability_requests": specialist_requests,
            "selected_specialist_capability": selected_capability, "node_id": node_id,
            "execution_profile": handoff["execution_profile"], "mutation_scope": mutation_scope,
            "validation_requirements": requirements, "context_manifest_ref": manifest_ref}
        routing_path = self.state_store.layout.snapshot(resolved_run_id, "orchestration-decision", sha256_json(routing_proof))
        write_immutable_json(routing_path, routing_proof)
        routing_ref = relative_ref(self.state_store.layout.root, routing_path)

        if _strategy_consumer is not None:
            accepted = _strategy_consumer({'handoff': handoff, 'proof_ref': routing_ref,
                'manifest_ref': manifest_ref, 'selection_inputs': selection_inputs,
                'project_facts': inputs['project_facts']})
            if not accepted:
                return {'schema_version': '2.0', 'status': 'blocked', 'run_id': resolved_run_id,
                    'reason': 'Adaptive strategy rejected prepared dispatch', 'results': [], 'evidence_refs': [],
                    'handoff': handoff, 'orchestration_decision_ref': routing_ref, 'context_manifest_ref': manifest_ref}

        evidence_refs: list[str] = []
        state_ref = self._save_execution_state(
            run_id=resolved_run_id,
            step_id=node_id,
            action_id=handoff["action_id"],
            status="running",
            evidence_refs=evidence_refs,
        )
        workflow_state_ref = self._save_workflow_state(
            run_id=resolved_run_id,
            route_id=route_id,
            node_id=node_id,
            evidence_refs=evidence_refs,
        )
        loop_id = str(entry_request.get("loop_id") or "") or None
        loop_state_ref = None
        if loop_id:
            loop_state_ref = self._save_loop_state(
                run_id=resolved_run_id,
                loop_id=loop_id,
                attempt=0,
                decision="continue",
                progress_marker=node_id,
            )

        if is_camera_fov_reference_request(effective_request):
            reference = execute_camera_fov_reference(
                entry_request=effective_request,
                project_root=entry_request["project_root"],
                persistence_root=self.state_store.layout.root,
                environment_snapshot=snapshot,
                context=context,
                executors=executors,
                provider_arguments=provider_arguments,
                broker=self.broker,
                evidence_store=self.evidence_store,
                approval_resolver=self.approval_resolver,
                run_id=resolved_run_id,
            )
            typed_action = reference.get("typed_action")
            reference_action_id = (
                str(typed_action.get("action_id"))
                if isinstance(typed_action, Mapping) and typed_action.get("action_id")
                else handoff["action_id"]
            )
            evidence_refs.extend(str(item) for item in reference.get("evidence_refs") or [])
            final_status = str(reference.get("status") or "blocked")
            state_ref = self._save_execution_state(
                run_id=resolved_run_id,
                step_id=node_id,
                action_id=reference_action_id,
                status=final_status,
                evidence_refs=evidence_refs,
            )
            workflow_state_ref = self._save_workflow_state(
                run_id=resolved_run_id,
                route_id=route_id,
                node_id=node_id,
                evidence_refs=evidence_refs,
            )
            if loop_id:
                loop_state_ref = self._save_loop_state(
                    run_id=resolved_run_id,
                    loop_id=loop_id,
                    attempt=1,
                    decision="exit" if final_status == "completed" else "blocked",
                    progress_marker=node_id,
                )
            result = {
                "schema_version": "1.0",
                "status": final_status,
                "run_id": resolved_run_id,
                "entry_point": entry_request["entry_point"],
                "layer_trace": ["entry", "control_plane", "reference_contract", "runtime_gate", "provider_layer", "evidence_state"],
                "handoff": handoff,
                "orchestration_decision_ref": routing_ref,
                "context_manifest_ref": manifest_ref,
                "results": [reference],
                "reference_action_id": reference_action_id,
                "evidence_refs": evidence_refs,
                "state_ref": state_ref,
                "workflow_state_ref": workflow_state_ref,
                "loop_state_ref": loop_state_ref,
            }
            return self._observe_strategy(result, current_path=execution_plan['path'])

        results: list[dict[str, Any]] = []
        runtime_provider_arguments = {name: dict(values) for name, values in (provider_arguments or {}).items()}
        specialist_execution_context = None
        csharp_session = None
        csharp_additions = {}
        csharp_error = False
        if intent['kind'] == 'csharp_local_fix':
            from unityagent.control_plane import csharp_fix
            try:
                from unityagent.control_plane.workspace_task_execution import WORKSPACE_DISPATCH_TOKEN
                csharp_session = csharp_fix.prepare(self, entry_request, context, handoff, manifest_ref=manifest_ref,
                    workspace_dispatch_authorized=_workspace_dispatch_token is WORKSPACE_DISPATCH_TOKEN)
                runtime_provider_arguments['file'] = csharp_session['file_arguments']
            except (ValueError, PersistenceError, OSError) as exc:
                csharp_error = True
                csharp_additions = {'status': 'blocked', 'reason': str(exc)}
                results.append({'status': 'blocked', 'capability': 'source.patch', 'reason': str(exc)})
        if specialist_selection["status"] == "selected":
            # The immutable manifest is the only Specialist Context source for the backend.
            specialist_execution_context = {
                "schema_version": "1.0",
                "context_id": view["context_id"],
                "context_fingerprint": view["context_fingerprint"]["value"],
                "specialist_context": deepcopy(view["specialist_context"]),
            }
        for index, request in enumerate(handoff["capability_requests"] if not csharp_error else []):
            if ((cancel_event is not None and cancel_event.is_set())
                    or (_execution_deadline is not None and time.monotonic() >= _execution_deadline)):
                results.append({'status': 'blocked', 'capability': request['capability'], 'reason': 'execution_cancelled'})
                break
            if csharp_session is not None:
                try:
                    csharp_fix.before_capability(self, csharp_session, request['capability'], resolved_run_id)
                except (ValueError, PersistenceError, OSError) as exc:
                    results.append({'status': 'blocked', 'capability': request['capability'], 'reason': str(exc)})
                    break
                runtime_provider_arguments['native_unity_editor'] = {
                    **runtime_provider_arguments.get('native_unity_editor', {}),
                    'run_id': f'{resolved_run_id}-cap{index + 1}', 'require_compilation_observation': True,
                    'cancel_event': cancel_event,
                    'test_filter': list(intent['editmode_tests'])}
                if _execution_deadline is not None:
                    native_arguments = runtime_provider_arguments['native_unity_editor']
                    native_arguments['timeout_seconds'] = min(native_arguments.get('timeout_seconds', 120.0),
                                                               max(.001, _execution_deadline - time.monotonic()))

            capability_step_id = f"{node_id}-{index + 1}"
            outcome = measured_call(self, resolved_run_id,
                'gate' if request['capability'] in {'static.review', 'compile.observe', 'project.test'} else 'provider', self.broker.dispatch,
                dict(request),
                snapshot,
                context=csharp_session['context'] if csharp_session is not None else context,
                executors=executors,
                provider_arguments=runtime_provider_arguments,
                specialist_execution_context=specialist_execution_context if request["capability"] == selected_capability else None,
                specialist_context_manifest_path=str(manifest_path.resolve()) if request["capability"] == selected_capability else None,
                receipt_required=specialist_selection["status"] == "selected" and request["capability"] == selected_capability and specialist_selection.get("receipt_required", True),
                maximum_retry_attempts=maximum_retry_attempts,
            )
            result = deepcopy(outcome)
            resolution = outcome.get("resolution")
            provider_result = outcome.get("provider_result")
            if (csharp_session is not None and request['capability'] == 'source.read'
                    and isinstance(provider_result, Mapping)):
                csharp_session['source'] = provider_result.get('content')
                provider_result = {key: value for key, value in provider_result.items() if key != 'content'}
                result['provider_result'] = provider_result
            if result.get("receipt_integrity") == "failed":
                results.append(result)
                break
            if isinstance(resolution, Mapping) and resolution.get("status") == "resolved" and isinstance(provider_result, Mapping):
                evidence_id = f"{resolved_run_id}-evidence-{index + 1}"
                observation_ref, observation_provenance = None, []
                if request["operation_kind"] == "read":
                    payload = observation_payload(request, provider_result)
                    payload_digest = sha256_json(payload)
                    payload_path = self.evidence_store.layout.snapshot(resolved_run_id, "observation", payload_digest)
                    write_immutable_json(payload_path, payload)
                    observation_ref = relative_ref(self.evidence_store.layout.root, payload_path)
                    observation_provenance = [f"observation_payload:{payload_digest}"]
                evidence = normalize_provider_result(
                    dict(request),
                    resolution,
                    snapshot,
                    provider_result,
                    run_id=resolved_run_id,
                    step_id=capability_step_id,
                    evidence_id=evidence_id,
                    structured_result_ref=observation_ref,
                    provenance_refs=observation_provenance,
                    definition_fingerprint=definition_fingerprint,
                    fallback_from=outcome.get("fallback_from"),
                    registry=self.broker.registry,
                )
                if csharp_session is not None:
                    from unityagent.runtime.guardrails.csharp_patch import project_revision as csharp_project_revision
                    evidence['execution_binding'] = {'patch_plan_id': csharp_session['plan']['plan_id'] if csharp_session['plan'] else csharp_session.get('evidence_plan_id'),
                        'input_project_revision': csharp_session['input_revision'],
                        'result_project_revision': csharp_project_revision(csharp_session['project']),
                        'context_manifest_ref': manifest_ref}
                persisted = append_runtime_execution_evidence(self.evidence_store, evidence)
                evidence_refs.append(str(persisted["evidence_id"]))
                result["evidence_ref"] = persisted["evidence_id"]
            results.append(result)
            state_ref = self._save_execution_state(
                run_id=resolved_run_id,
                step_id=capability_step_id,
                action_id=handoff["action_id"],
                status="running",
                evidence_refs=evidence_refs,
            )
            workflow_state_ref = self._save_workflow_state(
                run_id=resolved_run_id,
                route_id=route_id,
                node_id=capability_step_id,
                evidence_refs=evidence_refs,
            )

            if csharp_session is not None and not csharp_fix.after_capability(csharp_session, request['capability'], result):
                result['status'] = 'blocked'
                break

        if csharp_session is not None:
            try:
                if _execution_deadline is not None:
                    if time.monotonic() >= _execution_deadline:
                        raise ValueError('execution_deadline_expired')
                    reasoning_timeout_seconds = min(reasoning_timeout_seconds, _execution_deadline - time.monotonic())
                csharp_additions = csharp_fix.finish(self, csharp_session, handoff=handoff, manifest=manifest,
                    manifest_ref=manifest_ref, evidence_refs=evidence_refs, results=results, model=reasoning_model,
                    command_prefix=reasoning_command_prefix, timeout_seconds=reasoning_timeout_seconds,
                    reasoning_effort=reasoning_effort, cancel_event=cancel_event)
            except (ValueError, PersistenceError, OSError) as exc:
                csharp_additions = {'status': 'blocked', 'reason': str(exc)}

        if reasoning_action is not None and all(item.get("status") == "completed" for item in results):
            reasoning_output = self.state_store.layout.run_root(resolved_run_id) / "runtime" / node_id
            execution_result, artifact, artifact_ref = None, None, None
            try:
                required_observations = specialist_selection.get("required_observation_capabilities", [])
                if required_observations:
                    observations = []
                    for capability in required_observations:
                        matches = [item for item in results if item.get("capability") == capability and item.get("evidence_ref")]
                        if len(matches) != 1:
                            raise ContextBindingError(f"required observation has no unique durable evidence: {capability}")
                        evidence_id = matches[0]["evidence_ref"]
                        payload = self.evidence_store.read_observation(evidence_id, expected_run_id=resolved_run_id, expected_project_root=str(entry_request["project_root"]), expected_capability=capability)
                        record = self.evidence_store.verify_record(evidence_id, expected_run_id=resolved_run_id)
                        if record["definition_fingerprint"] != definition_fingerprint:
                            raise ContextBindingError(f"required observation definition differs from current execution: {capability}")
                        observations.append({"payload": payload, "record": record, "revision": sha256_json(payload)})
                    observed_items = inputs["specialist_items"] + observation_items(observations, inputs["specialist_tags"])
                    specialist_selection = resolve_specialist(route_id, selected_capability, snapshot, pilot_enabled=specialist_pilot_enabled, context_items=observed_items)
                    if specialist_selection["status"] != "selected":
                        raise ContextBindingError(f"Specialist Context gate: {specialist_selection.get('reason_code', specialist_selection['status'])}; required={specialist_selection.get('required_observations', [])}")
                    runtime_action = reasoning_action
                    route_decision["profile"] = "generic_planning"
                    previous_manifest_ref = manifest_ref
                    manifest = measured_call(self, resolved_run_id, 'context', build_context_manifest, resolved_run_id, route_id, project_facts=inputs["project_facts"], bindings=inputs["bindings"], capability_ids=capabilities, active_conditions=conditions, specialist_selection=specialist_selection, specialist_items=observed_items, specialist_tags=inputs["specialist_tags"], required_specialist_keys=inputs["required_specialist_keys"])
                    view = manifest["materialized_context"]
                    if manifest["budget_report"]["decision"] != "within_budget" or view["unresolved_bindings"]:
                        raise ContextBindingError(f"observed Context gate: {manifest['budget_report']['decision']}; unresolved={view['unresolved_bindings']}")
                    manifest_path = self.state_store.layout.snapshot(resolved_run_id, "context-manifest", sha256_json(manifest))
                    write_immutable_json(manifest_path, manifest)
                    manifest_ref = relative_ref(self.state_store.layout.root, manifest_path)
                    definition_fingerprint = {**definition_fingerprint, "policy_revision": view["definition_fingerprint"]["policy_revision"], "context_revision": view["definition_fingerprint"]["context_revision"]}
                    handoff = runtime_handoff(run_id=resolved_run_id, node_id=node_id, route_id=route_id, execution_profile=str(route_decision["profile"]), context_id=view["context_id"], context_fingerprint=view["context_fingerprint"]["value"], task_contract_runtime_projection=projection, mutation_scope=mutation_scope, validation_requirements=requirements, capability_requests=capability_requests, runtime_action=runtime_action, definition_fingerprint=dict(definition_fingerprint))
                    validate_runtime_handoff(handoff)
                    routing_proof = {**routing_proof, "context_manifest_ref": manifest_ref, "previous_context_manifest_ref": previous_manifest_ref, "observation_evidence_refs": [item["record"]["evidence_id"] for item in observations]}
                    routing_path = self.state_store.layout.snapshot(resolved_run_id, "orchestration-decision", sha256_json(routing_proof))
                    write_immutable_json(routing_path, routing_proof)
                    routing_ref = relative_ref(self.state_store.layout.root, routing_path)
                if not reasoning_model:
                    raise CodexRunnerError("host-selected reasoning model is unavailable")
                execution_result, artifact = execute_reasoning(handoff, manifest, original_project=Path(entry_request["project_root"]), output=reasoning_output, model=reasoning_model, model_revision=reasoning_model_revision, command_prefix=reasoning_command_prefix, timeout_seconds=reasoning_timeout_seconds, reasoning_effort=reasoning_effort)
                failure = execution_result.get("runtime_failure")
                if execution_result["status"] == "passed":
                    verify_reasoning_artifact(runtime_action["output_contract_ref"], manifest, artifact)
                    artifact_path = self.state_store.layout.snapshot(resolved_run_id, "reasoning-artifact", sha256_json(artifact))
                    write_immutable_json(artifact_path, artifact)
                    artifact_ref = relative_ref(self.state_store.layout.root, artifact_path)
                else:
                    artifact_ref = None
            except CodexRunnerError as exc:
                failure = {"failure_class": "runner_unavailable", "reason": str(exc)}
                execution_result, artifact, artifact_ref = None, None, None
            except (ContextBindingError, PersistenceError) as exc:
                failure = {"failure_class": "context_binding_failed", "reason": str(exc)}
                artifact_ref = None
            except ReasoningOutputError as exc:
                failure = {"failure_class": exc.failure_class, "reason": str(exc)}
                artifact_ref = None
            except ValueError as exc:
                failure = {"failure_class": "runtime_protocol_failure", "reason": str(exc)}
                artifact_ref = None
            if execution_result is not None and failure and execution_result["status"] == "passed":
                execution_result = {**execution_result, "status": "failed", "runtime_failure": {"schema_version": "1.0", "failure_class": failure["failure_class"], "reason": failure["reason"], "retryable": False, "source_ref": "response.json", "observation_state": "observed"}}
            reasoning_status = "completed" if artifact_ref else "blocked"
            outcome = {"status": reasoning_status, "capability": reasoning_action["capability"], "runtime_action": "specialist_reasoning", "output_contract_ref": reasoning_action["output_contract_ref"], "artifact_ref": artifact_ref, "runtime_failure": failure}
            if execution_result is not None:
                execution_path = self.state_store.layout.snapshot(resolved_run_id, "reasoning-execution", sha256_json(execution_result))
                write_immutable_json(execution_path, execution_result)
                outcome["execution_ref"] = relative_ref(self.state_store.layout.root, execution_path)
            evidence_id = f"{resolved_run_id}-reasoning-evidence"
            evidence = {"schema_version": "1.1", "evidence_id": evidence_id, "run_id": resolved_run_id, "step_id": node_id, "source_type": "reasoning_execution", "source_ref": outcome.get("execution_ref"), "timestamp": _now(), "hash": sha256_json(artifact) if artifact_ref else None, "producer": "Runtime/CodexRunner", "verification_status": "passed" if artifact_ref else "failed", "provenance": ["runtime_handoff", "codex_runner", "schema_validation", "semantic_validation", "context_binding", "workspace_mutation_observation"], "payload_ref": artifact_ref, "gate_outcome": None, "definition_fingerprint": dict(definition_fingerprint)}
            from unityagent.runtime.handoff.reasoning_runtime import normalize_reasoning_evidence
            evidence = normalize_reasoning_evidence(evidence, output_contract_ref=reasoning_action['output_contract_ref'],
                manifest=manifest, artifact=artifact, project_root=str(entry_request['project_root']))
            self.evidence_store.append(evidence)
            evidence_refs.append(evidence_id)
            outcome["evidence_ref"] = evidence_id
            results.append(outcome)

        final_status = csharp_additions.get("status", "completed" if all(item.get("status") == "completed" for item in results) else "blocked")
        state_ref = self._save_execution_state(
            run_id=resolved_run_id,
            step_id=node_id,
            action_id=handoff["action_id"],
            status=final_status,
            evidence_refs=evidence_refs,
        )
        workflow_state_ref = self._save_workflow_state(
            run_id=resolved_run_id,
            route_id=route_id,
            node_id=node_id,
            evidence_refs=evidence_refs,
        )
        result = {
            "schema_version": "1.0",
            "status": final_status,
            "run_id": resolved_run_id,
            "entry_point": entry_request["entry_point"],
            "layer_trace": ["entry", "control_plane", "capability_orchestration", "provider_layer", "evidence_state"],
            "handoff": handoff,
            "orchestration_decision_ref": routing_ref,
            "context_manifest_ref": manifest_ref,
            "results": results,
            "evidence_refs": evidence_refs,
            "state_ref": state_ref,
            "workflow_state_ref": workflow_state_ref,
            **csharp_additions,
        }
        return self._observe_strategy(result, current_path=execution_plan['path'])

    def execute_tasks(self, tasks, *, run_id, definition_fingerprint, task_parameters, resume=False, adaptive_strategy_enabled=False, root_contract=None, plan_proposer=None):
        """既存RuntimeへTask単位で渡し、固定Acceptanceを満たす依存だけを開く。"""
        from unityagent.control_plane.task_execution import execute_task_dag
        from unityagent.persistence.store.atomic_store import exclusive_file_lock
        with exclusive_file_lock(self.state_store.layout.run_root(run_id) / "task-execution.lock"), capture_persistence(self, run_id):
            return execute_task_dag(self, tasks, run_id=run_id,
                definition_fingerprint=definition_fingerprint, task_parameters=task_parameters, resume=resume,
                adaptive_strategy_enabled=adaptive_strategy_enabled, root_contract=root_contract, plan_proposer=plan_proposer)

    def execute_workspace_tasks(self, tasks, *, run_id, definition_fingerprint, task_parameters,
                                root_contract, parallel_enabled=False, resume=False, plan_proposer=None,
                                timeout_seconds=300.0, cancel_event=None):
        """別Projectの子Runを最大2件に制限し、親だけがPlanとAcceptanceを更新する。"""
        from unityagent.control_plane.workspace_task_execution import execute_workspace_dag
        from unityagent.persistence.store.atomic_store import exclusive_file_lock
        with exclusive_file_lock(self.state_store.layout.run_root(run_id) / 'task-execution.lock'), capture_persistence(self, run_id):
            if (len(tasks) == 1 and plan_proposer is None and cancel_event is None and timeout_seconds == 300.0
                    and isinstance(parallel_enabled, bool) and (not resume or
                    'parallel_execution' not in self.state_store.load_task_state(run_id))):
                from unityagent.control_plane.task_execution import execute_task_dag
                return execute_task_dag(self, tasks, run_id=run_id, definition_fingerprint=definition_fingerprint,
                    task_parameters=task_parameters, root_contract=root_contract, resume=resume)
            return execute_workspace_dag(self, tasks, run_id=run_id,
                definition_fingerprint=definition_fingerprint, task_parameters=task_parameters,
                root_contract=root_contract, parallel_enabled=parallel_enabled, resume=resume,
                plan_proposer=plan_proposer, timeout_seconds=timeout_seconds, cancel_event=cancel_event)

    def create_integration_plan(self, *, run_id):
        from unityagent.control_plane.csharp_integration import create_integration_plan
        from unityagent.persistence.store.atomic_store import exclusive_file_lock
        with exclusive_file_lock(self.state_store.layout.run_root(run_id) / 'task-execution.lock'), capture_persistence(self, run_id):
            return create_integration_plan(self, run_id)

    def approve_integration(self, *, integration_plan_id):
        from unityagent.control_plane.csharp_integration import approve_integration
        return approve_integration(self, integration_plan_id)

    def integrate_workspace_results(self, *, run_id, integration_plan_id, approval_ref,
                                    original_parameters=None, timeout_seconds=300.0, cancel_event=None):
        from unityagent.control_plane.csharp_integration import integrate_workspace_results, load_integration_plan
        from unityagent.persistence.store.atomic_store import exclusive_file_lock
        if original_parameters is None:
            from unityagent.runtime.tooling.environment.discovery import discover_environment
            from unityagent.runtime.tooling.providers.file.file_provider import FileProvider
            from unityagent.runtime.tooling.providers.native_unity_editor.native_unity_editor_provider import NativeUnityEditorProvider
            project = load_integration_plan(self, integration_plan_id)['project_root']
            snapshot = discover_environment(project, mutation_allowed_paths=['Assets']).to_dict()
            native = NativeUnityEditorProvider(project, snapshot,
                temp_root=self.state_store.layout.run_root(run_id) / 'integration-output')
            original_parameters = {'environment_snapshot': snapshot, 'context': ResolutionContext(policy_allowed=True),
                'executors': {'file': FileProvider(project).execute, 'native_unity_editor': native.execute}}
        with exclusive_file_lock(self.state_store.layout.run_root(run_id) / 'task-execution.lock'), capture_persistence(self, run_id):
            return measured_call(self, run_id, 'integration', integrate_workspace_results, self, run_id, integration_plan_id, approval_ref,
                original_parameters, timeout_seconds=timeout_seconds, cancel_event=cancel_event)

    def setup(
        self,
        entry_point: str,
        setup_request: dict[str, Any],
        *,
        executors: Mapping[str, Any],
        definition_fingerprint: Mapping[str, Any],
        executor_arguments: Mapping[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Route Codex/Unity UI setup through the Registry-selected Installer Provider."""
        if entry_point not in {"unity_ui", "codex_plugin"}:
            raise ValueError("unsupported Entry point")
        setup_request = {**setup_request, "entry_point": entry_point}
        validate_toolchain_setup_request(setup_request)
        validate_definition_fingerprint(dict(definition_fingerprint))
        resolved_run_id = run_id or _new_run_id(str(setup_request["request_id"]))
        step_id = "toolchain-setup"
        action_id = f"setup:{setup_request['operation']}"
        evidence_refs: list[str] = []
        state_ref = self._save_execution_state(
            run_id=resolved_run_id, step_id=step_id, action_id=action_id,
            status="running", evidence_refs=evidence_refs,
        )
        outcome = self.broker.dispatch_management(
            setup_request,
            executors=executors,
            executor_arguments=executor_arguments,
        )
        provider_result = outcome.get("provider_result")
        resolution = outcome.get("resolution")
        if isinstance(resolution, Mapping) and resolution.get("status") == "resolved" and isinstance(provider_result, Mapping):
            provider_result = deepcopy(provider_result)
            evidence_id = f"{resolved_run_id}-evidence-1"
            receipt = provider_result.get("install_receipt")
            if isinstance(receipt, Mapping):
                receipt = {
                    **dict(receipt),
                    "run_id": resolved_run_id,
                    "evidence_refs": [evidence_id],
                    "verified_at": str(receipt.get("verified_at") or _now()),
                }
                validate_install_receipt(receipt)
                provider_result["install_receipt"] = receipt
            receipt_ref = None
            outcome = {**outcome, "provider_result": provider_result}
            evidence = normalize_toolchain_result(
                provider_result,
                evidence_id=evidence_id,
                run_id=resolved_run_id,
                step_id=step_id,
                project_root=str(setup_request["project_root"]),
                definition_fingerprint=definition_fingerprint,
            )
            persisted = append_runtime_execution_evidence(self.evidence_store, evidence)
            evidence_refs.append(str(persisted["evidence_id"]))
            if isinstance(receipt, Mapping):
                receipt_ref = self.receipt_store.append(dict(receipt))
            outcome = {
                **outcome,
                "evidence_ref": persisted["evidence_id"],
                "receipt_ref": receipt_ref,
            }
        final_status = "completed" if outcome.get("status") == "completed" and provider_result and provider_result.get("status") == "passed" else "blocked"
        state_ref = self._save_execution_state(
            run_id=resolved_run_id, step_id=step_id, action_id=action_id,
            status=final_status, evidence_refs=evidence_refs,
        )
        return {
            "schema_version": "1.0",
            "status": final_status,
            "run_id": resolved_run_id,
            "entry_point": entry_point,
            "layer_trace": ["entry", "control_plane", "capability_orchestration", "provider_layer", "evidence_state"],
            "operation": setup_request["operation"],
            "outcome": outcome,
            "evidence_refs": evidence_refs,
            "state_ref": state_ref,
            "receipt_ref": outcome.get("receipt_ref"),
        }
