from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import threading
import time
import unittest
import uuid

from Persistence.Evidence.evidence_store import EvidenceStore
from Runtime.ReferenceImplementation.authority import (
    ApprovalDecisionResolver,
    BudgetExceeded,
    RuntimeBudgetLedger,
    SubAgentTaskPlanner,
    SurfaceGrantProjector,
    TaskContractIssuer,
)
from Runtime.ReferenceImplementation.canonicalization import CanonicalizationError, canonicalize, sha256_jcs
from Runtime.ReferenceImplementation.contracts import (
    ApprovalDecision,
    CompletionDecision,
    CompletionProof,
    ContractValidationError,
    EvidenceRecord,
    ProviderResult,
    TypedAction,
)
from Runtime.ReferenceImplementation.golden_task import GoldenTaskRunner
from Runtime.ReferenceImplementation.isolation import (
    IsolationViolation,
    RuntimeIPCProtocol,
    SpecialistCapabilitySurface,
    SpecialistSession,
)
from Runtime.ReferenceImplementation.runtime import (
    ActionReservationStore,
    CompletionCoordinator,
    EvidenceCompletionGate,
    IdempotencyLedger,
    ReservationState,
    RuntimeDispatchGate,
    append_reference_evidence,
)


ROOT = Path(__file__).resolve().parents[3]


class _PersistenceDirectory:
    def __enter__(self) -> str:
        self.path = ROOT / "Artifacts" / "reference-implementation" / f"persistence-test-{uuid.uuid4().hex}"
        self.path.mkdir(parents=True, exist_ok=False)
        return str(self.path)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def budgets() -> dict[str, int]:
    return {
        "max_parent_total_calls": 2, "max_parent_reentries": 0, "max_global_replans": 0, "max_escalations": 1,
        "max_child_llm_calls": 12, "max_tool_calls": 20, "max_wall_clock_ms": 120000, "max_child_wall_clock_ms": 60000,
        "max_child_input_tokens": 10000, "max_child_output_tokens": 10000, "max_parent_input_tokens": 20000,
        "max_parent_output_tokens": 10000, "max_process_restarts": 1, "max_provider_retries": 1,
    }


def contract_fixture():
    project = {"root": str(ROOT), "name": "reference-test-project"}
    task = TaskContractIssuer().issue(task_id="task-test", run_id="run-test", project=project, project_fingerprint=sha256_jcs(project), budgets=budgets(), issued_at=datetime.now(timezone.utc).isoformat())
    approval = ApprovalDecision.approve(approval_decision_id="approval-test", task=task, expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    resolver = ApprovalDecisionResolver()
    resolver.register(approval)
    trusted = resolver.resolve(approval.approval_decision_id, task=task)
    grant = SurfaceGrantProjector().derive(task=task, approval=trusted, subagent_instance_id="artist-test")
    action = TypedAction.propose(action_id="action-test", idempotency_key="idempotency-test", task=task, approval=trusted, grant=grant, value=43.0, expected_revision="revision-before")
    return task, trusted, grant, action


def provider_result(action: TypedAction, *, before: float = 40.0, after: float = 43.0, revision: str = "revision-after") -> ProviderResult:
    value = {
        "schema_version": "1.1", "status": "passed", "provider_ref": "unity_artist_cli", "action_id": action.action_id,
        "project": dict(action.project), "target": dict(action.target), "property_path": action.property_path,
        "before_value": before, "after_value": after, "observed_revision": revision,
        "exact_diff": {"target": action.target["guid"], "property": action.property_path, "before": before, "after": after},
        "evidence": ["mutation_diff", "editor_observation", "visual_capture"], "mutation_count": 1,
        "boundary_violations": [], "failure_class": None, "provider_result_digest": "",
    }
    value["provider_result_digest"] = sha256_jcs({key: item for key, item in value.items() if key != "provider_result_digest"})
    return ProviderResult.from_dict(value)


class ReferenceContractTests(unittest.TestCase):
    def test_jcs_is_stable_and_rejects_nan(self):
        self.assertEqual(canonicalize({"b": 1, "a": "x"}), '{"a":"x","b":1}')
        self.assertEqual(canonicalize({"negativeZero": -0.0}), '{"negativeZero":0}')
        self.assertEqual(canonicalize(1e-6), "0.000001")
        self.assertEqual(canonicalize(1e-7), "1e-7")
        self.assertEqual(canonicalize(1e20), "100000000000000000000")
        self.assertEqual(canonicalize(1e21), "1e+21")
        self.assertEqual(canonicalize(1.234567890123456e-5), "0.00001234567890123456")
        self.assertEqual(canonicalize({"\U00010000": 1, "\uffff": 2}), '{"𐀀":1,"\uffff":2}')
        with self.assertRaises(CanonicalizationError):
            canonicalize(float("nan"))

    def test_contracts_use_schema_validated_envelopes(self):
        task, approval, grant, action = contract_fixture()
        for contract in (task, approval, grant, action):
            envelope = contract.to_envelope()
            self.assertEqual(envelope["contract_type"], type(contract).__name__)
        self.assertEqual(TypedAction.from_envelope(action.to_envelope()).action_digest, action.action_digest)
        invalid = action.to_envelope()
        invalid["value"]["unexpected"] = True
        with self.assertRaises(ContractValidationError):
            TypedAction.from_envelope(invalid)

    def test_unknown_fields_and_cross_binding_fail_closed(self):
        task, approval, grant, action = contract_fixture()
        invalid = task.to_dict()
        invalid["unexpected"] = True
        with self.assertRaises(ContractValidationError):
            type(task).from_dict(invalid)
        wrong_action = action.to_dict()
        wrong_action["target"] = {"guid": "other-camera", "component_type": "UnityEngine.Camera"}
        with self.assertRaises(ContractValidationError):
            type(action).from_dict(wrong_action)

    def test_approval_revocation_expiry_and_installer_grant_exclusion(self):
        task, approval, grant, action = contract_fixture()
        resolver = ApprovalDecisionResolver()
        resolver.register(approval)
        resolver.revoke(approval.approval_decision_id)
        with self.assertRaises(ContractValidationError):
            resolver.resolve(approval.approval_decision_id, task=task)
        with self.assertRaises(ContractValidationError):
            SurfaceGrantProjector().derive(task=task, approval=approval, subagent_instance_id="artist-test", requested_capabilities=["installer.install"])


class MutationRuntimeTests(unittest.TestCase):
    def test_dispatch_re_resolves_revoked_approval_at_runtime_boundary(self):
        task, approval, grant, action = contract_fixture()
        resolver = ApprovalDecisionResolver()
        resolver.register(approval)
        resolver.revoke(approval.approval_decision_id)
        calls = 0

        def dispatch(_: TypedAction):
            nonlocal calls
            calls += 1
            return provider_result(action)

        with self.assertRaises(ContractValidationError):
            RuntimeDispatchGate(approval_resolver=resolver).dispatch(
                task=task, approval=approval, grant=grant, action=action, dispatch_provider=dispatch
            )
        self.assertEqual(calls, 0)

    def test_reservation_and_idempotency_survive_process_restart(self):
        task, approval, grant, action = contract_fixture()
        result = provider_result(action)
        with _PersistenceDirectory() as directory:
            first_gate = RuntimeDispatchGate(persistence_root=directory)
            first = first_gate.dispatch(
                task=task, approval=approval, grant=grant, action=action,
                dispatch_provider=lambda _: result, evidence_writer=lambda *_: ["evidence-1"],
            )
            self.assertEqual(first["status"], "applied")
            calls = 0

            def should_not_apply(_: TypedAction):
                nonlocal calls
                calls += 1
                return result

            second = RuntimeDispatchGate(persistence_root=directory).dispatch(
                task=task, approval=approval, grant=grant, action=action, dispatch_provider=should_not_apply,
            )
            self.assertEqual(second["status"], "idempotent")
            self.assertEqual(second["evidence_ids"], ["evidence-1"])
            self.assertEqual(calls, 0)

    def test_evidence_failure_is_in_doubt_and_recovery_does_not_reapply(self):
        task, approval, grant, action = contract_fixture()
        result = provider_result(action)
        with _PersistenceDirectory() as directory:
            calls = 0

            def apply_once(_: TypedAction):
                nonlocal calls
                calls += 1
                return result

            gate = RuntimeDispatchGate(persistence_root=directory)
            with self.assertRaises(RuntimeError):
                gate.dispatch(
                    task=task, approval=approval, grant=grant, action=action,
                    dispatch_provider=apply_once,
                    evidence_writer=lambda *_: (_ for _ in ()).throw(RuntimeError("evidence unavailable")),
                )
            self.assertEqual(gate.reservations.get(action).state, ReservationState.IN_DOUBT)
            recovered = RuntimeDispatchGate(persistence_root=directory).recover(
                task=task, approval=approval, grant=grant, action=action,
                evidence_writer=lambda *_: ["evidence-replayed"],
                observe=lambda _: {"value": 43.0, "revision": "revision-after"},
            )
            self.assertEqual(recovered["status"], "recovered")
            self.assertEqual(calls, 1)
            replay = RuntimeDispatchGate(persistence_root=directory).dispatch(
                task=task, approval=approval, grant=grant, action=action, dispatch_provider=apply_once,
            )
            self.assertEqual(replay["status"], "idempotent")
            self.assertEqual(replay["evidence_ids"], ["evidence-replayed"])
            self.assertEqual(calls, 1)
    def test_idempotent_replay_and_key_reuse(self):
        task, approval, grant, action = contract_fixture()
        result = provider_result(action)
        calls = 0

        def dispatch(_: TypedAction):
            nonlocal calls
            calls += 1
            return result

        gate = RuntimeDispatchGate()
        first = gate.dispatch(task=task, approval=approval, grant=grant, action=action, dispatch_provider=dispatch)
        second = gate.dispatch(task=task, approval=approval, grant=grant, action=action, dispatch_provider=dispatch)
        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "idempotent")
        self.assertEqual(calls, 1)
        different = TypedAction.propose(action_id="action-other", idempotency_key=action.idempotency_key, task=task, approval=approval, grant=grant, value=44.0, expected_revision=action.expected_revision)
        with self.assertRaises((ContractValidationError, RuntimeError)):
            gate.dispatch(task=task, approval=approval, grant=grant, action=different, dispatch_provider=dispatch)

    def test_concurrent_same_action_has_one_apply(self):
        task, approval, grant, action = contract_fixture()
        result = provider_result(action)
        calls = 0
        lock = threading.Lock()

        def dispatch(_: TypedAction):
            nonlocal calls
            with lock:
                calls += 1
            time.sleep(0.03)
            return result

        gate = RuntimeDispatchGate()
        outcomes: list[str] = []
        errors: list[Exception] = []

        def run() -> None:
            try:
                outcomes.append(gate.dispatch(task=task, approval=approval, grant=grant, action=action, dispatch_provider=dispatch)["status"])
            except Exception as exc:  # one concurrent claimant is expected to lose the reservation
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(5)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(calls, 1)
        self.assertEqual(outcomes.count("applied"), 1)
        self.assertEqual(len(outcomes) + len(errors), 5)

    def test_crash_recovery_reobserves_before_commit(self):
        task, approval, grant, action = contract_fixture()
        store = ActionReservationStore()
        store.reserve(action)
        store.mark_in_doubt(action)
        self.assertEqual(store.recover(action, observe=lambda: {"revision": "revision-after", "value": 43.0}), ReservationState.COMMITTED)

        action_two = TypedAction.propose(action_id="action-test-two", idempotency_key="idempotency-test-two", task=task, approval=approval, grant=grant, value=44.0, expected_revision="revision-before")
        store_two = ActionReservationStore()
        store_two.reserve(action_two)
        store_two.mark_in_doubt(action_two)
        self.assertEqual(store_two.recover(action_two, observe=lambda: {"revision": "revision-before", "value": 40.0}), ReservationState.ABORTED)

    def test_scope_expansion_and_postcondition_mismatch_are_rejected(self):
        task, approval, grant, action = contract_fixture()
        out_of_scope = action.to_dict()
        out_of_scope["property_path"] = "Camera.nearClipPlane"
        with self.assertRaises(ContractValidationError):
            type(action).from_dict(out_of_scope)
        gate = RuntimeDispatchGate()
        bad = provider_result(action, after=44.0)
        with self.assertRaises(ContractValidationError):
            gate.dispatch(task=task, approval=approval, grant=grant, action=action, dispatch_provider=lambda _: bad)


class CompletionAndIsolationTests(unittest.TestCase):
    def test_completion_gate_requires_all_durable_evidence(self):
        task, approval, grant, action = contract_fixture()
        result = provider_result(action)
        root = ROOT / "Artifacts" / "reference-implementation" / f"test-{uuid.uuid4().hex}"
        store = EvidenceStore(root)
        gate = RuntimeDispatchGate()

        def write_all(bound_action: TypedAction, bound_result: ProviderResult) -> list[str]:
            ids: list[str] = []
            for evidence_type, payload in (("mutation_diff", {"diff": bound_result.exact_diff}), ("editor_observation", {"revision": bound_result.observed_revision}), ("visual_capture", {"captured": True})):
                record = EvidenceRecord.observed(evidence_id=f"{bound_action.run_id}-{evidence_type}", task_id=task.task_id, run_id=task.run_id, action_id=bound_action.action_id, evidence_type=evidence_type, payload=payload)
                append_reference_evidence(store=store, task=task, action=bound_action, result=bound_result, evidence=record, evidence_type=evidence_type)
                ids.append(record.evidence_id)
            return ids

        dispatch = gate.dispatch(task=task, approval=approval, grant=grant, action=action, dispatch_provider=lambda _: result, evidence_writer=write_all)
        ledger = RuntimeBudgetLedger(task.budgets)
        decision = EvidenceCompletionGate(store).evaluate(task=task, approval=approval, grant=grant, actions=[action], provider_results=[result], reservations=gate.reservations, evidence_ids=dispatch["evidence_ids"], final_revision=result.observed_revision, ledger=ledger)
        self.assertEqual(decision.state, "eligible")
        missing = EvidenceCompletionGate(store).evaluate(task=task, approval=approval, grant=grant, actions=[action], provider_results=[result], reservations=gate.reservations, evidence_ids=dispatch["evidence_ids"][:2], final_revision=result.observed_revision, ledger=ledger)
        self.assertEqual(missing.state, "blocked")

    def test_ipc_replay_unknown_message_and_direct_installer_surface_fail(self):
        session = SpecialistSession("session-test", "artist-test", "00" * 16, r"\\.\pipe\reference-test", "task-test", "run-test", "grant-test", "11" * 32, "", "")
        protocol = RuntimeIPCProtocol(session)
        message = protocol.make("inspect", {"target_guid": "camera-guid-001", "property_path": "Camera.fieldOfView"})
        self.assertEqual(protocol.accept(message)["sequence"], 0)
        with self.assertRaises(IsolationViolation):
            protocol.accept(message)
        invalid = dict(message)
        invalid["sequence"] = 1
        invalid["message_type"] = "installer.install"
        with self.assertRaises(IsolationViolation):
            SpecialistCapabilitySurface.validate_message(invalid)

    def test_budget_overrun_cannot_be_converted_to_success(self):
        task, approval, grant, action = contract_fixture()
        ledger = RuntimeBudgetLedger(task.budgets)
        with self.assertRaises(BudgetExceeded):
            ledger.consume("parent_total_calls", 3)
        ledger.add_unbounded("parent_total_calls", 3)
        self.assertTrue(ledger.exhausted)

    def test_completion_coordinator_rejects_forged_decision(self):
        ledger = RuntimeBudgetLedger(budgets())
        forged = CompletionDecision(
            "1.1", "task-test", "run-test", "eligible", "revision-after", [], [],
            budgets(), [], "eligible", "00" * 32,
        )
        presented = CompletionCoordinator().present(forged, ledger=ledger)
        self.assertEqual(presented["status"], "blocked")
        with self.assertRaises(ContractValidationError):
            CompletionProof(forged, "forged-token", issuer=object())


@unittest.skipUnless(
    os.name == "nt" and os.environ.get("UNITYAGENT_RUN_GOLDEN_FIXTURE_TESTS") == "1",
    "GoldenArtistTransport is a fixture-only unit/E2E test; production validation uses the live Unity runner",
)
class GoldenTaskE2ETests(unittest.TestCase):
    def test_windows_camera_fov_golden_task(self):
        result = GoldenTaskRunner(ROOT / "Artifacts" / "reference-implementation" / f"golden-test-{uuid.uuid4().hex}").run()
        self.assertEqual(result["terminal"], "GOAL_COMPLETE")
        self.assertEqual(result["completion"]["state"], "eligible")
        self.assertEqual(result["camera"]["after"], 43.0)
        for name in ("approval_bypass_success", "scope_expansion_success", "direct_cli_bypass_success", "direct_installer_bypass_success", "duplicate_mutation_apply", "completion_without_required_evidence", "parent_per_tool_mediation", "runtime_validation_llm_calls"):
            self.assertEqual(result["metrics"][name], 0, name)


if __name__ == "__main__":
    unittest.main()
