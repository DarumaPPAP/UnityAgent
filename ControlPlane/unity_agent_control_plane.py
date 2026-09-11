"""Thin UnityAgent Control Plane over the existing Runtime chain.

This module is the only Entry-facing execution facade. It owns run identity and
durable state, asks Orchestration for a provider-independent handoff, and sends
capabilities to the existing ToolBroker. It deliberately contains no Provider
selection or direct subprocess invocation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator

from Orchestration.Orchestrator.orchestrator import runtime_handoff
from Orchestration.Graph.state_mapping import loop_control_state_patch, workflow_state_patch
from Persistence.Evidence.evidence_store import EvidenceStore
from Persistence.Evidence.runtime_adapter import append_runtime_execution_evidence
from Persistence.Install.receipt_store import InstallReceiptStore
from Persistence.State.state_store import StateStore
from Persistence.Contracts.definition_fingerprint import validate_definition_fingerprint
from Runtime.Contracts.install_receipt_contract import validate_install_receipt
from Runtime.EvidenceCapture.tool_runtime_evidence import normalize_provider_result
from Runtime.EvidenceCapture.toolchain_evidence import normalize_toolchain_result
from Runtime.Tooling.Environment.environment_snapshot import EnvironmentSnapshot
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.provider_registry import RuntimeProviderRegistry
from Runtime.Tooling.tool_broker import ToolBroker
from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Contracts.toolchain_setup_contract import validate_toolchain_setup_request

ROOT = Path(__file__).resolve().parents[1]
ENTRY_SCHEMA_PATH = Path("Runtime/Contracts/entry-request.schema.yaml")
PROVIDER_ID_KEYS = frozenset({"provider", "provider_ref", "provider_id"})


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
    schema = yaml.safe_load((root / ENTRY_SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
    if _contains_provider_identity(value):
        raise ValueError("Entry request must not contain Provider identity")
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
    ) -> None:
        self.broker = broker or ToolBroker()
        self.state_store = state_store or StateStore(persistence_root)
        self.evidence_store = evidence_store or EvidenceStore(persistence_root)
        self.receipt_store = receipt_store or InstallReceiptStore(persistence_root)

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
    ) -> dict[str, Any]:
        """Run Entry -> Orchestration -> ToolBroker -> Provider -> Evidence."""
        validate_entry_request(entry_request)
        validate_definition_fingerprint(dict(definition_fingerprint))
        snapshot = _snapshot_dict(environment_snapshot)
        resolved_run_id = run_id or _new_run_id(str(entry_request["request_id"]))
        node_id = str(entry_request.get("node_id") or "entry_runtime_action")
        handoff = runtime_handoff(
            run_id=resolved_run_id,
            node_id=node_id,
            route_id=str(entry_request["route_id"]),
            execution_profile=str(entry_request["execution_profile"]),
            context_id=str(entry_request["context_id"]),
            context_fingerprint=str(entry_request["context_fingerprint"]),
            task_contract_runtime_projection=dict(entry_request["task_contract_runtime_projection"]),
            mutation_scope=dict(entry_request["mutation_scope"]),
            validation_requirements=list(entry_request["validation_requirements"]),
            capability_requests=list(entry_request["capability_requests"]),
        )

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
            route_id=str(entry_request["route_id"]),
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
        results: list[dict[str, Any]] = []
        for index, request in enumerate(entry_request["capability_requests"]):
            capability_step_id = f"{node_id}-{index + 1}"
            outcome = self.broker.dispatch(
                dict(request),
                snapshot,
                context=context,
                executors=executors,
                provider_arguments=provider_arguments,
            )
            result = deepcopy(outcome)
            resolution = outcome.get("resolution")
            provider_result = outcome.get("provider_result")
            if isinstance(resolution, Mapping) and resolution.get("status") == "resolved" and isinstance(provider_result, Mapping):
                evidence_id = f"{resolved_run_id}-evidence-{index + 1}"
                evidence = normalize_provider_result(
                    dict(request),
                    resolution,
                    snapshot,
                    provider_result,
                    run_id=resolved_run_id,
                    step_id=capability_step_id,
                    evidence_id=evidence_id,
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
                route_id=str(entry_request["route_id"]),
                node_id=capability_step_id,
                evidence_refs=evidence_refs,
            )
            if loop_id:
                loop_state_ref = self._save_loop_state(
                    run_id=resolved_run_id,
                    loop_id=loop_id,
                    attempt=index + 1,
                    decision="continue",
                    progress_marker=capability_step_id,
                )

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
            route_id=str(entry_request["route_id"]),
            node_id=node_id,
            evidence_refs=evidence_refs,
        )
        if loop_id:
            loop_state_ref = self._save_loop_state(
                run_id=resolved_run_id,
                loop_id=loop_id,
                attempt=len(results),
                decision="exit" if final_status == "completed" else "blocked",
                progress_marker=node_id,
            )
        return {
            "schema_version": "1.0",
            "status": final_status,
            "run_id": resolved_run_id,
            "entry_point": entry_request["entry_point"],
            "layer_trace": ["entry", "control_plane", "capability_orchestration", "provider_layer", "evidence_state"],
            "handoff": handoff,
            "results": results,
            "evidence_refs": evidence_refs,
            "state_ref": state_ref,
            "workflow_state_ref": workflow_state_ref,
            "loop_state_ref": loop_state_ref,
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
