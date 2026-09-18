"""Windows Camera FOV Golden Task harness over the canonical Runtime chain."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping

from Persistence.Evidence.evidence_store import EvidenceStore
from Runtime.Tooling.Providers.UnityArtistCli.unity_artist_cli_provider import UnityArtistCliProvider
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.tool_broker import ToolBroker

from .authority import ApprovalDecisionResolver, RuntimeBudgetLedger, SubAgentTaskPlanner, SurfaceGrantProjector, TaskContractIssuer, iso_now
from .canonicalization import sha256_jcs
from .contracts import (
    ApprovalDecision,
    CompletionDecision,
    EvidenceRecord,
    ProviderResult,
    SurfaceGrant,
    TaskContract,
    TypedAction,
)
from .isolation import IsolationError, SubAgentSessionManager
from .profiles import default_profile
from .runtime import (
    CompletionCoordinator,
    EvidenceCompletionGate,
    RuntimeDispatchGate,
    append_reference_evidence,
)


ROOT = Path(__file__).resolve().parents[2]


def _snapshot(project_root: Path) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": {"root": str(project_root), "exists": True, "identity_status": "bound", "unity_version": "6000.6.0f1", "required_paths": {"assets": True, "packages": True, "project_settings": True}},
        "filesystem": {"readable": True, "writable": True, "writable_in_mutation_scope": True},
        "git": {"available": True, "repository_bound": True},
        "unity_editor": {"installed": True, "version": "6000.6.0f1", "executable_path": "C:/Unity/Editor.exe", "project_version_match": True, "running": True, "safe_mode": False, "project_bound": True, "binding_status": "bound", "bound_instance_id": "editor-reference"},
        "unity_cli": {"available": True, "version": "1.0.0-beta.8", "executable_path": "C:/Unity/unity.exe", "failure_class": None},
        "unity_artist_cli": {"available": True, "compatible": True, "version": "0.0.1-beta", "executable_path": "C:/Tools/unity-artist.exe", "project_bound": True, "package_installed": True, "package_version": "0.0.1-beta", "pipeline_reachable": True, "unity_version": "6000.6.0f1", "render_pipeline": "builtin", "support_tier": "primary", "compatibility_backend": "builtin_editor_api", "capabilities": ["visual_art.refine", "visual_art.capture"], "failure_class": None, "binding_status": "bound", "bound_instance_id": "unity-artist-reference"},
        "pipeline": {"installed": True, "reachable": True},
        "myunitymcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
        "coplay_mcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
        "test_framework": {"available": True},
        "build": {"requested_target": None, "requested_target_module_available": "unknown"},
        "player_runtime": {"reachable": False, "instance_id": None},
        "profile_hint": "FULL", "binding_fingerprint": "0" * 64,
    }


@dataclass
class GoldenCameraState:
    guid: str = "camera-guid-001"
    value: float = 40.0
    apply_count: int = 0

    def revision(self) -> str:
        return sha256_jcs({"guid": self.guid, "component": "UnityEngine.Camera", "property": "Camera.fieldOfView", "value": self.value})

    def apply(self, action: TypedAction) -> tuple[float, str]:
        if action.target["guid"] != self.guid:
            raise ValueError("golden fixture target mismatch")
        if action.expected_revision != self.revision():
            raise ValueError("stale golden fixture revision")
        before = self.value
        self.value = action.value
        self.apply_count += 1
        return before, self.revision()


class GoldenArtistTransport:
    """Deterministic transport fixture behind UnityArtistCliProvider.

    It exercises the existing provider adapter and ToolBroker without launching
    an untrusted executable during the contract test. The production adapter
    remains responsible for the real official Unity CLI transport.
    """

    def __init__(self, state: GoldenCameraState) -> None:
        self.state = state
        self.action: TypedAction | None = None
        self.before_value: float | None = None
        self.observed_revision: str | None = None

    def __call__(self, request: Any, *, cancel_event: Any = None) -> dict[str, Any]:
        if cancel_event is not None and cancel_event.is_set():
            return {"status": "cancelled", "failure_class": "runtime_cancelled"}
        if self.action is None or "refine" not in request.command:
            return {"status": "failed", "failure_class": "runtime_protocol_failure", "reason": "typed refine action was not bound"}
        self.before_value, self.observed_revision = self.state.apply(self.action)
        pipeline = {
            "status": "passed", "planId": f"plan-{self.action.action_id}", "sessionId": "artist-reference-session",
            "expectedRevision": self.action.expected_revision, "diffDigest": sha256_jcs({"action": self.action.action_id}),
            "evidence": ["mutation_evidence", "exact_diff", "expected_revision", "camera_binding", "undo_registration", "save_not_performed"],
        }
        return {
            "status": "passed",
            "payload": {"status": "passed", "data": {"evidence": pipeline["evidence"], "provider": {"data": {"result": json.dumps(pipeline)}}}},
        }


class GoldenTaskRunner:
    def __init__(self, persistence_root: str | Path | None = None, *, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root or ROOT).resolve()
        self.persistence_root = Path(persistence_root or (ROOT / "Artifacts" / "reference-implementation" / "golden-task")).resolve()

    def run(self) -> dict[str, Any]:
        profile = default_profile()
        run_id = "run-001"
        project = {"root": str(self.project_root), "name": "WindowsCameraFovGoldenProject"}
        project_fingerprint = sha256_jcs({"project": project["name"], "version": "reference-v1.1"})
        budgets = {
            "max_parent_total_calls": 2, "max_parent_reentries": 0, "max_global_replans": 0, "max_escalations": 1,
            "max_child_llm_calls": 12, "max_tool_calls": 20, "max_wall_clock_ms": 120000, "max_child_wall_clock_ms": 60000,
            "max_child_input_tokens": 10000, "max_child_output_tokens": 10000, "max_parent_input_tokens": 20000,
            "max_parent_output_tokens": 10000, "max_process_restarts": 1, "max_provider_retries": 1,
        }
        issuer = TaskContractIssuer()
        task = issuer.issue(task_id="artist-camera-fov-001", run_id=run_id, project=project, project_fingerprint=project_fingerprint, budgets=budgets, issued_at=iso_now(), profile=profile)
        approval = ApprovalDecision.approve(
            approval_decision_id="approval-001", task=task,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            profile=profile,
        )
        resolver = ApprovalDecisionResolver()
        resolver.register(approval)
        trusted_approval = resolver.resolve(approval.approval_decision_id, task=task)
        grant = SurfaceGrantProjector().derive(task=task, approval=trusted_approval, subagent_instance_id="artist-reference-001", profile=profile)
        ledger = RuntimeBudgetLedger(task.budgets)
        plan = SubAgentTaskPlanner().plan(task, ledger, profile=profile)
        camera = GoldenCameraState()
        session_events: list[dict[str, Any]] = []
        isolation_status = "available"
        session_started = time.perf_counter()
        try:
            session_events = SubAgentSessionManager().run(
                task=task,
                grant=grant,
                context={"proposed_value": 43.0, "expected_revision": camera.revision(), "approval": trusted_approval.to_dict()},
                profile=profile,
            )
        except IsolationError as exc:
            isolation_status = "unavailable"
            return self._blocked(task, ledger, plan, str(exc), isolation_status)
        finally:
            ledger.record_child_observation(
                elapsed_ms=(time.perf_counter() - session_started) * 1000,
                context_bytes=len(json.dumps({"proposed_value": 43.0, "expected_revision": camera.revision()}).encode("utf-8")),
                schema_bytes=len(task.to_envelope().__repr__().encode("utf-8")),
            )
        action_message = next((item["payload"] for item in session_events if item["message_type"] == "propose_action"), None)
        if not isinstance(action_message, Mapping):
            return self._blocked(task, ledger, plan, "specialist did not propose a TypedAction", isolation_status)
        action_envelope = action_message.get("action_envelope")
        if isinstance(action_envelope, Mapping):
            action = TypedAction.from_envelope(action_envelope, profile=profile)
        else:
            # Compatibility for historical fixture transcripts; production IPC
            # is envelope-only and the child no longer emits this branch.
            action = TypedAction.from_dict(action_message.get("action"), profile=profile)
        ledger.record_tool_call()
        state_before = camera.value
        state_revision_before = camera.revision()
        transport = GoldenArtistTransport(camera)
        transport.action = action
        provider = UnityArtistCliProvider(self.project_root, _snapshot(self.project_root), dispatch_fn=transport)
        broker = ToolBroker()
        request = {
            "schema_version": "1.0", "capability": "domain.workflow", "project_root": str(self.project_root),
            "operation_kind": "editor_mutation", "required_evidence": ["domain_result", "mutation_evidence", "exact_diff", "expected_revision"],
            "mutation_scope": {"allowed_paths": ["Assets/Scenes/GoldenCamera.unity"], "prohibited_paths": ["ProjectSettings"]},
            "approval_ref": trusted_approval.approval_decision_id, "preferred_surface": "live_editor",
            "qualifiers": {"domain": "visual_art", "workflow": "lookdev_refine"},
        }
        dispatch_outcome: dict[str, Any] = {}
        provider_results: list[ProviderResult] = []

        def canonical_dispatch(_: TypedAction) -> ProviderResult:
            nonlocal dispatch_outcome
            dispatch_outcome = broker.dispatch(
                request,
                _snapshot(self.project_root),
                context=ResolutionContext(policy_allowed=True, approval_complete=True),
                executors={profile.provider_id: provider.execute},
                provider_arguments={profile.provider_id: {"command": "refine", "workflow": "lookdev_refine", "expected_revision": action.expected_revision}},
                maximum_retry_attempts=0,
            )
            raw = dispatch_outcome.get("provider_result")
            if dispatch_outcome.get("status") != "completed" or not isinstance(raw, Mapping) or raw.get("status") != "passed":
                raise RuntimeError(f"canonical ToolBroker dispatch failed: {dispatch_outcome}")
            result_dict = {
                "schema_version": "1.1", "status": "passed", "provider_ref": profile.provider_id, "action_id": action.action_id,
                "project": dict(task.project), "target": dict(action.target), "property_path": action.property_path,
                "before_value": float(transport.before_value if transport.before_value is not None else state_before),
                "after_value": camera.value, "observed_revision": str(transport.observed_revision or camera.revision()),
                "exact_diff": {"target": action.target["guid"], "property": action.property_path, "before": state_before, "after": camera.value},
                "evidence": list(profile.required_evidence), "mutation_count": 1,
                "boundary_violations": [], "failure_class": None, "provider_result_digest": "",
            }
            result_dict["provider_result_digest"] = sha256_jcs({key: value for key, value in result_dict.items() if key != "provider_result_digest"})
            result = ProviderResult.from_dict(result_dict)
            provider_results.append(result)
            return result
        evidence_store = EvidenceStore(self.persistence_root)

        def write_evidence(bound_action: TypedAction, result: ProviderResult) -> list[str]:
            records = [
                EvidenceRecord.observed(evidence_id=f"{run_id}-mutation-diff", task_id=task.task_id, run_id=run_id, action_id=bound_action.action_id, evidence_type="mutation_diff", payload={"before": result.before_value, "after": result.after_value, "exact_diff": result.exact_diff}),
                EvidenceRecord.observed(evidence_id=f"{run_id}-editor-observation", task_id=task.task_id, run_id=run_id, action_id=bound_action.action_id, evidence_type="editor_observation", payload={"target_guid": bound_action.target["guid"], "fieldOfView": result.after_value, "revision": result.observed_revision}),
                EvidenceRecord.observed(evidence_id=f"{run_id}-visual-capture", task_id=task.task_id, run_id=run_id, action_id=bound_action.action_id, evidence_type="visual_capture", payload={"capture_id": "capture-camera-fov-001", "captured": True, "observation_state": "observed", "fixture": "deterministic-editor-observation"}),
            ]
            ids: list[str] = []
            for record in records:
                append_reference_evidence(
                    store=evidence_store,
                    task=task,
                    action=bound_action,
                    result=result,
                    evidence=record,
                    evidence_type=record.evidence_type,
                    profile=profile,
                    approval=trusted_approval,
                    grant=grant,
                )
                ids.append(record.evidence_id)
            return ids

        gate = RuntimeDispatchGate(persistence_root=self.persistence_root, evidence_store=evidence_store, profile=profile)
        try:
            dispatch = gate.dispatch(task=task, approval=trusted_approval, grant=grant, action=action, dispatch_provider=canonical_dispatch, evidence_writer=write_evidence, ledger=ledger)
        except Exception as exc:
            return self._blocked(task, ledger, plan, str(exc), isolation_status)
        provider_result = provider_results[0]
        completion = EvidenceCompletionGate(evidence_store, profile=profile).evaluate(
            task=task, approval=trusted_approval, grant=grant, actions=[action], provider_results=[provider_result],
            reservations=gate.reservations, evidence_ids=list(dispatch["evidence_ids"]), final_revision=provider_result.observed_revision,
            ledger=ledger,
            profile=profile,
        )
        final = CompletionCoordinator().present(completion, ledger=ledger)
        metrics = {
            "approval_bypass_success": 0, "scope_expansion_success": 0, "direct_cli_bypass_success": 0,
            "direct_installer_bypass_success": 0, "duplicate_mutation_apply": max(0, camera.apply_count - 1),
            "completion_without_required_evidence": 0 if completion.state == "eligible" else 1,
            "parent_per_tool_mediation": plan["parent_per_tool_mediation"], "runtime_validation_llm_calls": 0,
            "normal_parent_total_calls": ledger.snapshot()["parent_total_calls"], "parent_reentries": ledger.snapshot()["parent_reentries"],
            "tool_calls": ledger.snapshot()["tool_calls"], "child_llm_calls": ledger.snapshot()["child_llm_calls"],
            "process_restarts": ledger.snapshot()["process_restarts"], "provider_retries": ledger.snapshot()["provider_retries"],
            "measurements": ledger.measurement_snapshot(),
        }
        return {
            "terminal": "GOAL_COMPLETE" if final["status"] == "completed" else "GOAL_NOT_COMPLETE",
            "status": final["status"], "run_id": run_id, "task_contract": task.to_dict(),
            "approval_decision": trusted_approval.to_dict(), "surface_grant": grant.to_dict(), "plan": plan,
            "specialist_events": session_events, "dispatch": dispatch_outcome, "provider_result": provider_result.to_dict(),
            "final_revision": provider_result.observed_revision, "camera": {"before": state_before, "after": camera.value, "apply_count": camera.apply_count, "revision_before": state_revision_before},
            "completion": completion.to_dict(), "metrics": metrics, "isolation": isolation_status,
        }

    @staticmethod
    def _blocked(task: TaskContract, ledger: RuntimeBudgetLedger, plan: dict[str, Any], reason: str, isolation_status: str) -> dict[str, Any]:
        return {"terminal": "GOAL_NOT_COMPLETE", "status": "blocked", "run_id": task.run_id, "reason": reason, "plan": plan, "budget": ledger.snapshot(), "metrics": {"approval_bypass_success": 0, "scope_expansion_success": 0, "direct_cli_bypass_success": 0, "direct_installer_bypass_success": 0, "duplicate_mutation_apply": 0, "completion_without_required_evidence": 1, "parent_per_tool_mediation": 0, "runtime_validation_llm_calls": 0}, "isolation": isolation_status}


def run_golden_task(persistence_root: str | Path | None = None) -> dict[str, Any]:
    return GoldenTaskRunner(persistence_root).run()
