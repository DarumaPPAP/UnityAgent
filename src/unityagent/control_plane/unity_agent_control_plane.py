"""Thin UnityAgent Control Plane over the existing Runtime chain.

This module is the only Entry-facing execution facade. It owns run identity and
durable execution/workflow state, asks Orchestration for a provider-independent
handoff, and sends capabilities to the existing ToolBroker. Semantic Local Loop
decisions are owned by src/unityagent/orchestration/loop and are never inferred from unityagent.runtime
capability iteration here.
"""
from __future__ import annotations
from unityagent.resources import resource_root

from datetime import datetime, timezone
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator

from unityagent.orchestration.orchestrator.orchestrator import runtime_handoff, runtime_node_for_requests
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
from unityagent.persistence.store.atomic_store import PersistenceError, relative_ref, sha256_json, write_immutable_json
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
    else:
        for request in value["capability_requests"]:
            validate_capability_request(dict(request), root=root)
            if str(request["project_root"]).casefold() != str(value["project_root"]).casefold():
                raise ValueError("CapabilityRequest project_root must match Entry project_root")


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
    ) -> dict[str, Any]:
        """Run Entry and Orchestration through the selected runtime handoff, then record Evidence."""
        validate_entry_request(entry_request)
        if entry_request["schema_version"] == "1.0":
            raise ValueError("Entry v1 migration required: use v2 without caller-supplied Context identity")
        validate_definition_fingerprint(dict(definition_fingerprint))
        snapshot = _snapshot_dict(environment_snapshot)
        resolved_run_id = run_id or _new_run_id(str(entry_request["request_id"]))
        intent = dict(entry_request["intent"])
        try:
            task_fingerprint = task_fingerprint_from_intent(intent, snapshot,
                project_root=str(entry_request["project_root"]), policy_allowed=context.policy_allowed)
            route_decision = select_route(task_fingerprint, load_routes(ROOT / "src/unityagent/orchestration/routing/task-routes.yaml"))
            route_id = str(route_decision["route_id"])
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
            projection = task_contract_projection(route_id)
            requirements = list(dict.fromkeys(evidence for request in capability_requests
                for evidence in request["required_evidence"]))
            node_id = runtime_node_for_requests(capability_requests,
                graph_path=ROOT / "src/unityagent/orchestration/definitions/development-parent-graph.yaml")
            capabilities = [str(request["capability"]) for request in capability_requests]
        except ValueError as exc:
            return {"schema_version": "2.0", "status": "blocked", "run_id": resolved_run_id,
                    "reason": str(exc), "results": [], "evidence_refs": []}
        try:
            inputs = derive_context_inputs(str(entry_request["project_root"]), snapshot, intent)
        except ValueError as exc:
            return {"schema_version": "2.0", "status": "blocked", "run_id": resolved_run_id, "reason": str(exc), "results": [], "evidence_refs": []}
        specialist_selection = resolve_specialist(route_id, selected_capability or capabilities[0], snapshot, pilot_enabled=specialist_pilot_enabled, context_items=inputs["specialist_items"], activation_only=True)
        if specialist_selection["status"] in {"unavailable", "unsupported"}:
            return {"schema_version": "2.0", "status": "blocked", "run_id": resolved_run_id,
                    "reason": f"Specialist {specialist_selection['status']}: {selected_capability}", "results": [], "evidence_refs": []}
        project_path = Path(entry_request["project_root"]).resolve()
        persistence_roots = (self.state_store.layout.root, self.evidence_store.layout.root)
        if specialist_selection.get("provider_resolution") == "not_required" and any(root == project_path or project_path in root.parents for root in persistence_roots):
            return {"schema_version": "2.0", "status": "blocked", "run_id": resolved_run_id, "reason": "reasoning Persistence root must be outside the original Project", "results": [], "evidence_refs": []}
        try:
            manifest = build_context_manifest(resolved_run_id, route_id, project_facts=inputs["project_facts"],
                bindings=inputs["bindings"], capability_ids=capabilities, active_conditions=conditions,
                specialist_selection=specialist_selection if specialist_selection["status"] != "activated" else None,
                specialist_items=inputs["specialist_items"] if specialist_selection["status"] == "selected" else None,
                specialist_tags=inputs["specialist_tags"] if specialist_selection["status"] == "selected" else None,
                required_specialist_keys=inputs["required_specialist_keys"] if specialist_selection["status"] == "selected" else None)
        except ValueError as exc:
            return {"schema_version": "2.0", "status": "blocked", "run_id": resolved_run_id,
                    "reason": str(exc), "results": [], "evidence_refs": []}
        view = manifest["materialized_context"]
        manifest_path = self.state_store.layout.snapshot(resolved_run_id, "context-manifest", sha256_json(manifest))
        write_immutable_json(manifest_path, manifest)
        manifest_ref = relative_ref(self.state_store.layout.root, manifest_path)
        if manifest["budget_report"]["decision"] != "within_budget" or view["unresolved_bindings"]:
            return {"schema_version": "2.0", "status": "blocked", "run_id": resolved_run_id,
                    "reason": f"Context gate: {manifest['budget_report']['decision']}; unresolved={view['unresolved_bindings']}",
                    "context_manifest_ref": manifest_ref, "results": [], "evidence_refs": []}
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
        routing_proof = {"task_fingerprint": task_fingerprint, "route_decision": route_decision,
            "active_conditions": sorted(conditions), "task_contract_projection": projection,
            "capability_requests": handoff["capability_requests"], "specialist_capability_requests": specialist_requests,
            "selected_specialist_capability": selected_capability, "node_id": node_id,
            "execution_profile": handoff["execution_profile"], "mutation_scope": mutation_scope,
            "validation_requirements": requirements, "context_manifest_ref": manifest_ref}
        routing_path = self.state_store.layout.snapshot(resolved_run_id, "orchestration-decision", sha256_json(routing_proof))
        write_immutable_json(routing_path, routing_proof)
        routing_ref = relative_ref(self.state_store.layout.root, routing_path)

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
            return {
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

        results: list[dict[str, Any]] = []
        runtime_provider_arguments = {name: dict(values) for name, values in (provider_arguments or {}).items()}
        specialist_execution_context = None
        if specialist_selection["status"] == "selected":
            # The immutable manifest is the only Specialist Context source for the backend.
            specialist_execution_context = {
                "schema_version": "1.0",
                "context_id": view["context_id"],
                "context_fingerprint": view["context_fingerprint"]["value"],
                "specialist_context": deepcopy(view["specialist_context"]),
            }
        for index, request in enumerate(handoff["capability_requests"]):
            capability_step_id = f"{node_id}-{index + 1}"
            outcome = self.broker.dispatch(
                dict(request),
                snapshot,
                context=context,
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
                    manifest = build_context_manifest(resolved_run_id, route_id, project_facts=inputs["project_facts"], bindings=inputs["bindings"], capability_ids=capabilities, active_conditions=conditions, specialist_selection=specialist_selection, specialist_items=observed_items, specialist_tags=inputs["specialist_tags"], required_specialist_keys=inputs["required_specialist_keys"])
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
            self.evidence_store.append(evidence)
            evidence_refs.append(evidence_id)
            outcome["evidence_ref"] = evidence_id
            results.append(outcome)

        final_status = "completed" if all(item.get("status") == "completed" for item in results) else "blocked"
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
        return {
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
        }

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
