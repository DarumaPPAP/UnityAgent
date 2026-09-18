from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

from Persistence.Evidence.evidence_store import EvidenceStore
from Persistence.Approval.approval_store import ApprovalDecisionStore
from Persistence.Reference.reference_gate_store import ReferenceGateStore
from Persistence.State.state_store import StateStore
from Persistence.Store.atomic_store import PersistenceError
from Runtime.ReferenceImplementation.authority import (
    ApprovalDecisionResolver,
    RuntimeBudgetLedger,
    SurfaceGrantProjector,
    TaskContractIssuer,
)
from Runtime.ReferenceImplementation.canonicalization import sha256_jcs
from Runtime.ReferenceImplementation.contracts import (
    ApprovalDecision,
    ContractValidationError,
    EvidenceRecord,
    ProviderResult,
    TypedAction,
)
from Runtime.ReferenceImplementation.runtime import (
    ActionReservationStore,
    EvidenceCompletionGate,
    IdempotencyLedger,
    ReservationState,
    RuntimeDispatchGate,
    _profile_binding_digest,
    append_reference_evidence,
    reference_definition_fingerprint,
    validate_reference_environment_snapshot,
)
from Runtime.ReferenceImplementation.profiles import default_profile
from Runtime.Tooling.Environment.project_identity import canonical_scene_path


ROOT = Path(__file__).resolve().parents[3]


def _budgets() -> dict[str, int]:
    return {
        "max_parent_total_calls": 2,
        "max_parent_reentries": 0,
        "max_global_replans": 0,
        "max_escalations": 0,
        "max_child_llm_calls": 2,
        "max_tool_calls": 10,
        "max_wall_clock_ms": 120000,
        "max_child_wall_clock_ms": 60000,
        "max_child_input_tokens": 1000,
        "max_child_output_tokens": 1000,
        "max_parent_input_tokens": 1000,
        "max_parent_output_tokens": 1000,
        "max_process_restarts": 1,
        "max_provider_retries": 1,
    }


def _fixture(project_root: Path | None = None, *, run_id: str = "hardening-run"):
    profile = default_profile()
    root = project_root or ROOT
    project = {"root": str(root.resolve()), "name": "issue-136-project"}
    project_fingerprint = sha256_jcs({"project": project, "version": "reference-v1.1"})
    task = TaskContractIssuer().issue(
        task_id=f"task-{run_id}",
        run_id=run_id,
        project=project,
        project_fingerprint=project_fingerprint,
        budgets=_budgets(),
        scope=profile.default_scope,
        issued_at=datetime.now(timezone.utc).isoformat(),
        profile=profile,
    )
    approval = ApprovalDecision.approve(
        approval_decision_id=f"approval-{run_id}",
        task=task,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        lower=35.0,
        upper=50.0,
        profile=profile,
    )
    resolver = ApprovalDecisionResolver()
    resolver.register(approval)
    grant = SurfaceGrantProjector().derive(
        task=task,
        approval=approval,
        subagent_instance_id=f"artist-{run_id}",
        profile=profile,
    )
    action = TypedAction.propose(
        action_id=f"action-{run_id}",
        idempotency_key=f"idempotency-{run_id}",
        task=task,
        approval=approval,
        grant=grant,
        value=43.0,
        expected_revision="revision-before",
        profile=profile,
    )
    value = {
        "schema_version": "1.1",
        "status": "passed",
        "provider_ref": profile.provider_id,
        "action_id": action.action_id,
        "project": dict(action.project),
        "target": dict(action.target),
        "property_path": action.property_path,
        "before_value": 40.0,
        "after_value": 43.0,
        "observed_revision": "revision-after",
        "exact_diff": {
            "target": action.target["guid"],
            "property": action.property_path,
            "before": 40.0,
            "after": 43.0,
        },
        "evidence": list(profile.required_evidence),
        "mutation_count": 1,
        "boundary_violations": [],
        "failure_class": None,
        "provider_result_digest": "",
    }
    value["provider_result_digest"] = sha256_jcs(
        {key: item for key, item in value.items() if key != "provider_result_digest"}
    )
    return profile, task, approval, resolver, grant, action, ProviderResult.from_dict(value)


def _writer(store: EvidenceStore, task, approval, grant, profile, *, capture: dict | None = None, scene_path: str | None = None, environment_snapshot: dict | None = None):
    def write(action: TypedAction, result: ProviderResult) -> list[str]:
        ids: list[str] = []
        for evidence_type in profile.required_evidence:
            payload: dict[str, object] = {
                "observed": True,
                "value": result.after_value,
            }
            if evidence_type == "visual_capture" and capture is not None:
                payload["capture"] = dict(capture)
            record = EvidenceRecord.observed(
                evidence_id=f"{action.run_id}-{evidence_type}",
                task_id=task.task_id,
                run_id=task.run_id,
                action_id=action.action_id,
                evidence_type=evidence_type,
                payload=payload,
                profile=profile,
            )
            append_reference_evidence(
                store=store,
                task=task,
                action=action,
                result=result,
                evidence=record,
                evidence_type=evidence_type,
                profile=profile,
                approval=approval,
                grant=grant,
                scene_path=scene_path,
                environment_snapshot=environment_snapshot,
            )
            ids.append(record.evidence_id)
        return ids

    return write


class Issue136HardeningTests(unittest.TestCase):
    def test_control_plane_state_binds_committed_typed_action(self) -> None:
        """The persisted terminal state must name the mutation, not its route node."""
        from ControlPlane import unity_agent_control_plane as control_plane_module

        request = {
            "schema_version": "1.0",
            "request_id": "reference-state-binding",
            "entry_point": "codex_plugin",
            "project_root": str(ROOT.resolve()),
            "intent": {"kind": "camera_fov_reference"},
            "route_id": "camera_fov_reference",
            "node_id": "camera-fov-reference",
            "execution_profile": "camera_fov_reference",
            "context_id": "context-reference-state",
            "context_fingerprint": "reference-state-fingerprint",
            "task_contract_runtime_projection": {},
            "mutation_scope": {},
            "validation_requirements": ["project_fact"],
            "capability_requests": [{
                "schema_version": "1.0",
                "capability": "project.inspect",
                "project_root": str(ROOT.resolve()),
                "operation_kind": "read",
                "required_evidence": ["project_fact"],
                "mutation_scope": None,
                "approval_ref": None,
                "preferred_surface": "project",
            }],
        }
        fake_reference = {
            "status": "completed",
            "typed_action": {"action_id": "typed-action-reference-state"},
            "evidence_refs": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(control_plane_module, "is_camera_fov_reference_request", return_value=True), mock.patch.object(
                control_plane_module, "execute_camera_fov_reference", return_value=fake_reference
            ):
                result = control_plane_module.UnityAgentControlPlane(directory).execute(
                    request,
                    environment_snapshot={},
                    context=type("Context", (), {})(),
                    executors={},
                    definition_fingerprint=reference_definition_fingerprint(),
                    run_id="reference-state-run",
                )
            state = control_plane_module.StateStore(directory).load_execution_state(result["run_id"])
            self.assertEqual(state["current_action_id"], "typed-action-reference-state")
            self.assertEqual(result["reference_action_id"], "typed-action-reference-state")

    def test_missing_writer_blocks_before_provider_mutation(self) -> None:
        profile, task, approval, resolver, grant, action, result = _fixture()
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            gate = RuntimeDispatchGate(
                persistence_root=directory,
                evidence_store=store,
                approval_resolver=resolver,
                profile=profile,
            )
            calls = 0

            def provider(_: TypedAction):
                nonlocal calls
                calls += 1
                return result

            with self.assertRaises(ContractValidationError):
                gate.dispatch(
                    task=task,
                    approval=approval,
                    grant=grant,
                    action=action,
                    dispatch_provider=provider,
                    evidence_writer=None,
                )
            self.assertEqual(calls, 0)
            self.assertFalse(ReferenceGateStore(directory).layout.reference_idempotency(task.run_id).exists())

    def test_evidence_write_failure_leaves_in_doubt_and_never_committed(self) -> None:
        profile, task, approval, resolver, grant, action, result = _fixture()
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            gate = RuntimeDispatchGate(
                persistence_root=directory,
                evidence_store=store,
                approval_resolver=resolver,
                profile=profile,
            )

            def failing_writer(bound_action: TypedAction, bound_result: ProviderResult) -> list[str]:
                append_reference_evidence(
                    store=store,
                    task=task,
                    action=bound_action,
                    result=bound_result,
                    evidence=EvidenceRecord.observed(
                        evidence_id=f"{bound_action.run_id}-mutation_diff",
                        task_id=task.task_id,
                        run_id=task.run_id,
                        action_id=bound_action.action_id,
                        evidence_type="mutation_diff",
                        payload={"observed": True},
                        profile=profile,
                    ),
                    evidence_type="mutation_diff",
                    profile=profile,
                    approval=approval,
                    grant=grant,
                )
                raise OSError("durable evidence volume is unavailable")

            with self.assertRaises(OSError):
                gate.dispatch(
                    task=task,
                    approval=approval,
                    grant=grant,
                    action=action,
                    dispatch_provider=lambda _: result,
                    evidence_writer=failing_writer,
                )
            reservation = gate.reservations.get(action)
            self.assertIsNotNone(reservation)
            self.assertEqual(reservation.state, ReservationState.IN_DOUBT)
            persisted = ReferenceGateStore(directory).load_idempotency(task.run_id)["records"]
            self.assertEqual(len(persisted), 1)
            self.assertEqual(next(iter(persisted.values()))["state"], ReservationState.IN_DOUBT)
            self.assertNotEqual(reservation.state, ReservationState.COMMITTED)

    def test_record_tamper_blocks_idempotent_replay_without_provider_call(self) -> None:
        profile, task, approval, resolver, grant, action, result = _fixture()
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            writer = _writer(store, task, approval, grant, profile)
            first_gate = RuntimeDispatchGate(
                persistence_root=directory,
                evidence_store=store,
                approval_resolver=resolver,
                profile=profile,
            )
            first_gate.dispatch(
                task=task,
                approval=approval,
                grant=grant,
                action=action,
                dispatch_provider=lambda _: result,
                evidence_writer=writer,
            )
            evidence_path = store.layout.evidence(f"{task.run_id}-mutation_diff")
            tampered = store.get(f"{task.run_id}-mutation_diff")
            tampered["provider_ref"] = "attacker"
            evidence_path.write_text(__import__("json").dumps(tampered), encoding="utf-8")

            calls = 0

            def provider(_: TypedAction):
                nonlocal calls
                calls += 1
                return result

            replay_gate = RuntimeDispatchGate(
                persistence_root=directory,
                evidence_store=store,
                approval_resolver=resolver,
                profile=profile,
            )
            with self.assertRaises(ContractValidationError):
                replay_gate.dispatch(
                    task=task,
                    approval=approval,
                    grant=grant,
                    action=action,
                    dispatch_provider=provider,
                    evidence_writer=writer,
                )
            self.assertEqual(calls, 0)

    def test_capture_asset_tamper_blocks_replay(self) -> None:
        with tempfile.TemporaryDirectory() as project_directory, tempfile.TemporaryDirectory() as persistence_directory:
            project = Path(project_directory)
            (project / "Assets").mkdir()
            (project / "Packages").mkdir()
            (project / "ProjectSettings").mkdir()
            scene = project / "Assets" / "Main.unity"
            scene.write_text("Scene", encoding="utf-8")
            capture_path = project / "Artifacts" / "capture.png"
            capture_path.parent.mkdir()
            capture_path.write_bytes(b"png-capture-v1")
            profile, task, approval, resolver, grant, action, result = _fixture(project)
            capture = {
                "colorPath": str(capture_path),
                "bytes": capture_path.stat().st_size,
                "sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            }
            store = EvidenceStore(persistence_directory)
            writer = _writer(store, task, approval, grant, profile, capture=capture, scene_path="Assets/Main.unity")
            gate = RuntimeDispatchGate(
                persistence_root=persistence_directory,
                evidence_store=store,
                approval_resolver=resolver,
                profile=profile,
            )
            gate.dispatch(
                task=task,
                approval=approval,
                grant=grant,
                action=action,
                dispatch_provider=lambda _: result,
                evidence_writer=writer,
                scene_path="Assets/Main.unity",
            )
            capture_path.write_bytes(b"png-capture-tampered")
            replay_gate = RuntimeDispatchGate(
                persistence_root=persistence_directory,
                evidence_store=store,
                approval_resolver=resolver,
                profile=profile,
            )
            with self.assertRaises(ContractValidationError):
                replay_gate.dispatch(
                    task=task,
                    approval=approval,
                    grant=grant,
                    action=action,
                    dispatch_provider=lambda _: result,
                    evidence_writer=writer,
                    scene_path="Assets/Main.unity",
                )

    def test_environment_digest_is_part_of_evidence_binding(self) -> None:
        profile, task, approval, resolver, grant, action, result = _fixture()
        environment = {"observed": "editor-instance-a", "binding": "a"}
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            gate = RuntimeDispatchGate(
                persistence_root=directory,
                evidence_store=store,
                approval_resolver=resolver,
                profile=profile,
            )
            gate.dispatch(
                task=task,
                approval=approval,
                grant=grant,
                action=action,
                dispatch_provider=lambda _: result,
                evidence_writer=_writer(store, task, approval, grant, profile, environment_snapshot=environment),
                environment_snapshot=environment,
            )
            replay = RuntimeDispatchGate(
                persistence_root=directory,
                evidence_store=store,
                approval_resolver=resolver,
                profile=profile,
            )
            with self.assertRaises(ContractValidationError):
                replay.dispatch(
                    task=task,
                    approval=approval,
                    grant=grant,
                    action=action,
                    dispatch_provider=lambda _: result,
                    evidence_writer=_writer(store, task, approval, grant, profile, environment_snapshot={"observed": "editor-instance-b", "binding": "b"}),
                    environment_snapshot={"observed": "editor-instance-b", "binding": "b"},
                )

    def test_persisted_run_reuse_uses_canonical_hash_and_binding_gate(self) -> None:
        with tempfile.TemporaryDirectory() as project_directory, tempfile.TemporaryDirectory() as persistence_directory:
            project = Path(project_directory)
            (project / "Assets").mkdir()
            (project / "Packages").mkdir()
            (project / "ProjectSettings").mkdir()
            scene = project / "Assets" / "Main.unity"
            scene.write_text("scene", encoding="utf-8")
            capture_path = project / "Artifacts" / "capture.png"
            capture_path.parent.mkdir()
            capture_path.write_bytes(b"reuse-capture")
            fake_editor = project / "fake-unity-editor.exe"
            fake_cli = project / "fake-unity-cli.exe"
            fake_artist = project / "fake-unity-artist.exe"
            for executable in (fake_editor, fake_cli, fake_artist):
                executable.write_bytes(b"test executable")
            profile, task, approval, resolver, grant, action, result = _fixture(project, run_id="reuse-run")
            environment = {
                "schema_version": "1.0",
                "project": {
                    "root": str(project.resolve()),
                    "exists": True,
                    "identity_status": "bound",
                    "unity_version": "6000.6.0f1",
                    "required_paths": {"assets": True, "packages": True, "project_settings": True},
                },
                "filesystem": {"readable": True, "writable": True, "writable_in_mutation_scope": True},
                "git": {"available": True, "repository_bound": True},
                "unity_editor": {
                    "installed": True,
                    "version": "6000.6.0f1",
                    "executable_path": str(fake_editor),
                    "project_version_match": True,
                    "running": True,
                    "safe_mode": False,
                    "project_bound": True,
                    "binding_status": "bound",
                    "bound_instance_id": "editor-reuse",
                },
                "unity_cli": {"available": True, "version": "1.0.0", "executable_path": str(fake_cli), "failure_class": None},
                "unity_artist_cli": {
                    "available": True,
                    "version": "1.0.0",
                    "executable_path": str(fake_artist),
                    "project_bound": True,
                    "package_installed": True,
                    "package_version": "1.0.0",
                    "pipeline_reachable": True,
                    "compatible": True,
                    "unity_version": "6000.6.0f1",
                    "render_pipeline": "builtin",
                    "support_tier": "primary",
                    "compatibility_backend": "builtin_editor_api",
                    "capabilities": ["artist.camera.refine", "visual.capture"],
                    "failure_class": None,
                    "binding_status": "bound",
                    "bound_instance_id": "artist-reuse",
                },
                "pipeline": {"installed": True, "reachable": True},
                "myunitymcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
                "coplay_mcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
                "test_framework": {"available": True},
                "build": {"requested_target": None, "requested_target_module_available": "unknown"},
                "player_runtime": {"reachable": False, "instance_id": None},
                "profile_hint": "FULL",
                "binding_fingerprint": "a" * 64,
            }
            capture = {
                "colorPath": str(capture_path),
                "bytes": capture_path.stat().st_size,
                "sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            }
            store = EvidenceStore(persistence_directory)
            writer = _writer(store, task, approval, grant, profile, capture=capture, scene_path="Assets/Main.unity", environment_snapshot=environment)
            gate = RuntimeDispatchGate(
                persistence_root=persistence_directory,
                evidence_store=store,
                approval_resolver=resolver,
                profile=profile,
            )
            dispatched = gate.dispatch(
                task=task,
                approval=approval,
                grant=grant,
                action=action,
                dispatch_provider=lambda _: result,
                evidence_writer=writer,
                scene_path="Assets/Main.unity",
                environment_snapshot=environment,
            )
            ApprovalDecisionStore(persistence_directory).register(approval)
            StateStore(persistence_directory).save_execution_state({
                "schema_version": "1.0",
                "run_id": task.run_id,
                "status": "completed",
                "current_step_id": action.action_id,
                "current_action_id": action.action_id,
                "evidence_refs": list(dispatched["evidence_ids"]),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            ReferenceGateStore(persistence_directory).save_manifest(task.run_id, {
                "schema_version": "1.2",
                "run_id": task.run_id,
                "task_contract": task.to_dict(),
                "approval_decision": approval.to_dict(),
                "surface_grant": grant.to_dict(),
                "typed_action": action.to_dict(),
                "profile_id": profile.profile_id,
                "profile_digest": _profile_binding_digest(profile),
                "environment_snapshot": environment,
                "environment_snapshot_digest": sha256_jcs(environment),
                "project_root": task.project["root"],
                "project_fingerprint": task.project_fingerprint,
                "scene_path": "Assets/Main.unity",
                "provider_result": result.to_dict(),
                "evidence_ids": list(dispatched["evidence_ids"]),
            })
            reused = EvidenceCompletionGate.verify_persisted_run(
                run_id=task.run_id,
                persistence_root=persistence_directory,
                project_root=project,
                scene_path="Assets/Main.unity",
                expected_before_fov=40.0,
                expected_after_fov=43.0,
            )
            self.assertTrue(reused["reused"])
            manifest_path = ReferenceGateStore(persistence_directory).layout.reference_manifest(task.run_id)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["provider_result"]["after_value"] = 44.0
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ContractValidationError):
                EvidenceCompletionGate.verify_persisted_run(
                    run_id=task.run_id,
                    persistence_root=persistence_directory,
                    project_root=project,
                    scene_path="Assets/Main.unity",
                )

    def test_recovery_requires_causal_proof_even_when_value_matches(self) -> None:
        profile, task, approval, resolver, grant, action, result = _fixture()
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            reservations = ActionReservationStore(ReferenceGateStore(directory))
            reservations.reserve(action)
            reservations.mark_applied(action, result)
            reservations.mark_in_doubt(action)
            status = reservations.recover(
                action,
                observe=lambda: {"value": 43.0, "revision": "revision-after"},
            )
            self.assertEqual(status, ReservationState.ABORTED)
            self.assertEqual(reservations.get(action).recovery_reason, "equal value lacks this-run mutation causality proof")

    def test_run_scoped_persistence_and_interleaved_evidence_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile_a, task_a, approval_a, resolver_a, grant_a, action_a, result_a = _fixture(run_id="run-a")
            profile_b, task_b, approval_b, resolver_b, grant_b, action_b, result_b = _fixture(run_id="run-b")
            store = EvidenceStore(directory)
            reservations = ActionReservationStore(ReferenceGateStore(directory))
            reservations.reserve(action_a)
            reservations.reserve(action_b)
            idempotency = IdempotencyLedger(ReferenceGateStore(directory))
            self.assertIsNone(idempotency.begin(action_a))
            self.assertIsNone(idempotency.begin(action_b))
            self.assertEqual({item["run_id"] for item in ReferenceGateStore(directory).load_reservations("run-a")["records"].values()}, {"run-a"})
            self.assertEqual({item["run_id"] for item in ReferenceGateStore(directory).load_reservations("run-b")["records"].values()}, {"run-b"})
            _writer(store, task_a, approval_a, grant_a, profile_a)(action_a, result_a)
            _writer(store, task_b, approval_b, grant_b, profile_b)(action_b, result_b)
            self.assertTrue(store.layout.evidence_events("run-a").is_file())
            self.assertTrue(store.layout.evidence_events("run-b").is_file())
            store.verify_record("run-a-mutation_diff", expected_run_id="run-a")
            store.verify_record("run-b-mutation_diff", expected_run_id="run-b")

            bad = ReferenceGateStore(directory).load_reservations("run-b")
            ReferenceGateStore(directory).layout.reference_reservations("run-a").write_text(
                __import__("json").dumps(bad), encoding="utf-8"
            )
            with self.assertRaises(PersistenceError):
                ReferenceGateStore(directory).load_reservations("run-a")

    def test_separate_runtime_instances_cannot_double_apply_one_persisted_claim(self) -> None:
        profile, task, approval, resolver, grant, action, result = _fixture()
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            gates = [
                RuntimeDispatchGate(
                    persistence_root=directory,
                    evidence_store=store,
                    approval_resolver=resolver,
                    profile=profile,
                )
                for _ in range(2)
            ]
            calls = 0
            calls_lock = threading.Lock()
            outcomes: list[str] = []
            errors: list[Exception] = []

            def provider(_: TypedAction):
                nonlocal calls
                with calls_lock:
                    calls += 1
                time.sleep(0.03)
                return result

            def run(gate: RuntimeDispatchGate) -> None:
                try:
                    outcomes.append(gate.dispatch(
                        task=task,
                        approval=approval,
                        grant=grant,
                        action=action,
                        dispatch_provider=provider,
                        evidence_writer=_writer(store, task, approval, grant, profile),
                    )["status"])
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=run, args=(gate,)) for gate in gates]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(calls, 1)
            self.assertEqual(outcomes, ["applied"])
            self.assertEqual(len(errors), 1)

    def test_scene_path_is_canonical_and_rejects_traversal_and_link_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Assets").mkdir()
            scene = root / "Assets" / "Scene.unity"
            scene.write_text("scene", encoding="utf-8")
            outside = root.parent / f"issue-136-outside-{os.getpid()}.unity"
            outside.write_text("outside", encoding="utf-8")
            try:
                self.assertEqual(canonical_scene_path(root, "Assets/./Scene.unity"), "Assets/Scene.unity")
                with self.assertRaises(ValueError):
                    canonical_scene_path(root, "Assets/../issue-136-outside.unity", require_exists=False)
                with self.assertRaises(ValueError):
                    canonical_scene_path(root, str(outside))
                link = root / "Assets" / "Link.unity"
                try:
                    link.symlink_to(outside)
                except (OSError, NotImplementedError):
                    self.skipTest("このWindowsホストではsymlink作成権限がありません")
                with self.assertRaises(ValueError):
                    canonical_scene_path(root, "Assets/Link.unity")
            finally:
                try:
                    outside.unlink()
                except OSError:
                    pass

    def test_token_snapshot_never_labels_unknown_dimensions_as_zero(self) -> None:
        ledger = RuntimeBudgetLedger(_budgets())
        initial = ledger.measurement_snapshot()
        self.assertFalse(initial["measured"])
        self.assertEqual(initial["token_measurement"]["status"], "unmeasured")
        self.assertIsNone(initial["parent"]["input_tokens"])
        self.assertIsNone(initial["child"]["output_tokens"])
        ledger.record_child_llm_call(input_tokens=0, output_tokens=0)
        partial = ledger.measurement_snapshot()
        self.assertFalse(partial["measured"])
        self.assertEqual(partial["token_measurement"]["status"], "partial")
        self.assertEqual(partial["child"]["input_tokens"], 0)
        self.assertIsNone(partial["parent"]["output_tokens"])

    def test_named_pipe_acl_has_no_everyone_generic_all_or_global_patch(self) -> None:
        source = (ROOT / "Runtime" / "ReferenceImplementation" / "isolation.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, re.compile(r"_winapi\.(CreateNamedPipe|Listener|PipeConnection)\s*="))
        self.assertNotIn("Everyone", source)
        self.assertNotIn(";;;WD", source)
        self.assertIn("D:(A;;GRGW;;;{current_user_sid})", source)

    def test_clean_gate_restore_is_explicit_before_no_restore_build(self) -> None:
        source = (ROOT / "Tools" / "reference_implementation_final_gate.py").read_text(encoding="utf-8")
        restore = source.index('restore_command = ["dotnet", "restore"')
        build = source.index('build_command = ["dotnet", "build"')
        self.assertLess(restore, build)
        self.assertIn('"--no-restore"', source[build:])

    def test_live_publish_restores_a_clean_checkout_before_no_restore_publish(self) -> None:
        from Tools import run_camera_fov_reference_live as live_runner

        with tempfile.TemporaryDirectory() as directory:
            artist_root = Path(directory)
            project_file = artist_root / "src" / "UnityArtist.Cli" / "UnityArtist.Cli.csproj"
            project_file.parent.mkdir(parents=True)
            project_file.write_text("<Project />", encoding="utf-8")
            commands: list[list[str]] = []

            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                commands.append(list(command))
                if command[0] == "dotnet" and command[1] == "publish":
                    output = Path(command[command.index("-o") + 1])
                    output.mkdir(parents=True, exist_ok=True)
                    (output / "unity-artist.exe").write_bytes(b"published")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(live_runner, "_run", side_effect=fake_run):
                resolved = live_runner._publish_or_resolve_artist_cli(artist_root)
            self.assertEqual(resolved.name, "unity-artist.exe")
            self.assertGreaterEqual(len(commands), 2)
            self.assertEqual(commands[0][0:2], ["dotnet", "restore"])
            self.assertEqual(commands[1][0:2], ["dotnet", "publish"])
            self.assertIn("--no-restore", commands[1])

    def test_environment_validation_fails_closed_on_unobserved_fact(self) -> None:
        from Runtime.ReferenceImplementation.golden_task import _snapshot

        snapshot = _snapshot(ROOT)
        snapshot["filesystem"]["writable"] = "unknown"
        with self.assertRaises(ContractValidationError):
            validate_reference_environment_snapshot(snapshot, project_root=ROOT, scene_path="Assets/Scene.unity")


if __name__ == "__main__":
    unittest.main()
