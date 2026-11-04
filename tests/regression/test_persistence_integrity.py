"""Persistenceの実保存・不変レコード・Evidence改竄検出を検証する。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import subprocess
import sys
from copy import deepcopy
from unittest.mock import patch

from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.persistence.checkpoint.checkpoint_store import CheckpointStore
from unityagent.persistence.resume.resume import evaluate_resume

from jsonschema import Draft202012Validator, RefResolver
import yaml

from unityagent.persistence.contracts.definition_fingerprint import DEFINITION_FIELDS
from unityagent.persistence.evidence.evidence_store import EvidenceStore
from unityagent.persistence.state.state_store import StateStore
from unityagent.persistence.store.atomic_store import (
    PersistenceError,
    atomic_write_json,
    canonical_json,
    read_json,
    resolve_ref,
    sha256_json,
    write_immutable_json,
)


def evidence_record(*, evidence_id: str, run_id: str) -> dict:
    """テストが所有する記録。実Approvalや実Editorの成功を意味しない。"""
    return {
        "schema_version": "1.0",
        "evidence_id": evidence_id,
        "run_id": run_id,
        "step_id": "step-A",
        "source_type": "regression-test",
        "source_ref": "unit-test",
        "timestamp": "2026-01-01T00:00:00Z",
        "hash": "sha256:sample-payload",
        "producer": "unittest",
        "verification_status": "passed",
        "provenance": ["test_source:regression"],
        "definition_fingerprint": {
            "schema_version": "1.0",
            **{field: "fixture-v1" for field in DEFINITION_FIELDS},
        },
    }


class PersistenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="unityagent-persistence-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_evidence_fixture_conforms_to_canonical_schema(self):
        contracts = Path(__file__).resolve().parents[2] / "src/unityagent/persistence/contracts"
        schema = yaml.safe_load((contracts / "evidence-record.schema.yaml").read_text(encoding="utf-8"))
        fingerprint = yaml.safe_load((contracts / "definition-fingerprint.schema.yaml").read_text(encoding="utf-8"))
        resolver = RefResolver.from_schema(schema, store={fingerprint["$id"]: fingerprint})
        record = evidence_record(evidence_id="evidence-A", run_id="run-A")

        errors = list(Draft202012Validator(schema, resolver=resolver).iter_errors(record))

        self.assertEqual([(list(error.path), error.message) for error in errors], [])

    def test_immutable_record_rejects_conflicting_replacement(self):
        path = self.root / "snapshots" / "snapshot.json"
        self.assertTrue(write_immutable_json(path, {"value": "initial"}))
        self.assertFalse(write_immutable_json(path, {"value": "initial"}))

        with self.assertRaises(PersistenceError) as captured:
            write_immutable_json(path, {"value": "replacement"})

        self.assertEqual(captured.exception.code, "immutable_record_conflict")
        self.assertEqual(read_json(path), {"value": "initial"})

    def test_corrupted_json_fails_closed(self):
        path = self.root / "record.json"
        path.write_text('{"status":', encoding="utf-8")

        with self.assertRaises(PersistenceError) as captured:
            read_json(path)

        self.assertEqual(captured.exception.code, "record_corrupt")

    def test_persistence_reference_cannot_escape_root(self):
        with self.assertRaises(PersistenceError) as captured:
            resolve_ref(self.root, "../other-run/record.json")

        self.assertEqual(captured.exception.code, "path_escape_forbidden")

    def test_execution_state_rejects_wrong_run_identity(self):
        store = StateStore(self.root)
        record = {
            "schema_version": "1.0",
            "run_id": "run-A",
            "status": "running",
            "current_step_id": "step-A",
            "current_action_id": "action-A",
            "evidence_refs": [],
            "updated_at": "2026-01-01T00:00:00Z",
        }
        store.save_execution_state(record)
        self.assertEqual(StateStore(self.root).load_execution_state("run-A"), record)
        path = store.layout.execution_state("run-A")
        atomic_write_json(path, {**record, "run_id": "run-B"})

        with self.assertRaises(PersistenceError) as captured:
            store.load_execution_state("run-A")

        self.assertEqual(captured.exception.code, "state_identity_mismatch")

    def test_persisted_evidence_record_tamper_is_detected(self):
        store = EvidenceStore(self.root)
        record = evidence_record(evidence_id="evidence-A", run_id="run-A")
        self.assertTrue(store.append(record))
        self.assertEqual(
            EvidenceStore(self.root).verify_record("evidence-A", expected_run_id="run-A"),
            record,
        )
        path = store.layout.evidence("evidence-A")
        atomic_write_json(path, {**record, "verification_status": "failed"})

        with self.assertRaises(PersistenceError) as captured:
            store.verify_record("evidence-A", expected_run_id="run-A")

        self.assertEqual(captured.exception.code, "evidence_tampered")

    def test_event_chain_rejects_broken_link_with_valid_event_hash(self):
        store = EvidenceStore(self.root)
        store.append(evidence_record(evidence_id="evidence-A", run_id="run-A"))
        store.append(evidence_record(evidence_id="evidence-B", run_id="run-A"))
        self.assertEqual(len(EvidenceStore(self.root).verify_event_chain(expected_run_id="run-A")), 2)
        path = store.layout.evidence_events("run-A")
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        events[1]["previous_event_hash"] = sha256_json({"unrelated_event": True})
        # 自身のハッシュは整合させ、前イベントとの連結検査だけで拒否させる。
        events[1]["event_hash"] = sha256_json({key: value for key, value in events[1].items() if key != "event_hash"})
        path.write_text("".join(canonical_json(event) + "\n" for event in events), encoding="utf-8")

        with self.assertRaises(PersistenceError) as captured:
            store.verify_event_chain(expected_run_id="run-A")

        self.assertEqual(captured.exception.code, "evidence_event_tampered")

    def test_event_chain_rejects_invalid_event_hash_with_valid_link(self):
        store = EvidenceStore(self.root)
        store.append(evidence_record(evidence_id="evidence-A", run_id="run-A"))
        store.append(evidence_record(evidence_id="evidence-B", run_id="run-A"))
        self.assertEqual(len(EvidenceStore(self.root).verify_event_chain(expected_run_id="run-A")), 2)
        path = store.layout.evidence_events("run-A")
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        # 前イベントへの参照を保ち、内容と自身のハッシュの不一致だけを作る。
        events[1]["record_hash"] = sha256_json({"other_record": True})
        path.write_text("".join(canonical_json(event) + "\n" for event in events), encoding="utf-8")

        with self.assertRaises(PersistenceError) as captured:
            store.verify_event_chain(expected_run_id="run-A")

        self.assertEqual(captured.exception.code, "evidence_event_tampered")

    def test_cross_run_evidence_read_is_rejected(self):
        store = EvidenceStore(self.root)
        store.append(evidence_record(evidence_id="evidence-A", run_id="run-A"))

        with self.assertRaises(PersistenceError) as captured:
            store.verify_record("evidence-A", expected_run_id="run-B")

        self.assertEqual(captured.exception.code, "run_scope_mismatch")

    def test_unverified_schema_cannot_be_reused_as_read_observation(self):
        store = EvidenceStore(self.root)
        store.append(evidence_record(evidence_id="evidence-A", run_id="run-A"))

        with self.assertRaises(PersistenceError) as captured:
            store.read_observation(
                "evidence-A",
                expected_run_id="run-A",
                expected_project_root=str(self.root),
                expected_capability="project.read",
            )

        self.assertEqual(captured.exception.code, "observation_unverified")


class CheckpointRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="ua-cp-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.states = StateStore(self.root)
        self.fingerprint = {"schema_version": "1.0", **{field: "v1" for field in DEFINITION_FIELDS}}
        self.execution = {"schema_version": "1.0", "run_id": "run-A", "status": "waiting", "current_step_id": "step-A", "current_action_id": None, "active_tool_invocation_ref": None, "evidence_refs": ["ev-A"], "updated_at": "2026-01-01T00:00:00Z"}
        self.workflow = {"schema_version": "1.0", "run_id": "run-A", "parent_graph_id": "graph-A", "active_subgraph_id": None, "active_node_id": "node-A", "shared_state_refs": [], "gate_state_refs": [], "updated_at": "2026-01-01T00:00:00Z"}
        self.loop = {"schema_version": "1.0", "run_id": "run-A", "loop_id": "loop-A", "semantic_attempt": 1, "progress_marker": "inspected", "decision": "continue", "updated_at": "2026-01-01T00:00:00Z"}
        self.states.save_execution_state(self.execution)
        self.states.save_workflow_state(self.workflow)
        self.states.save_loop_control_state(self.loop)
        self.evidence = EvidenceStore(self.root)
        self.evidence.append(evidence_record(evidence_id="ev-A", run_id="run-A"))

    def checkpoint(self, **overrides):
        parameters = {"checkpoint_id": "cp-A", "run_id": "run-A", "reason": "safe-boundary", "loop_ids": ["loop-A"], "evidence_refs": ["ev-A"], "definition_fingerprint": self.fingerprint}
        parameters.update(overrides)
        return CheckpointStore(self.root).create(**parameters)

    def resume(self, fingerprint=None):
        return evaluate_resume(store_root=self.root, run_id="run-A", checkpoint_id="cp-A", current_definition_fingerprint=fingerprint or self.fingerprint)

    def test_resume_and_restore_exact_state_preserves_later_evidence(self):
        checkpoint = self.checkpoint()
        self.states.save_execution_state({**self.execution, "status": "failed"})
        self.states.save_loop_control_state({**self.loop, "loop_id": "later-loop"})
        self.evidence.append(evidence_record(evidence_id="ev-later", run_id="run-A"))
        before_evidence = {path: path.read_bytes() for path in (self.root / "evidence").rglob("*.json")}
        self.assertEqual(self.resume()["decision"], "resume")
        CheckpointStore(self.root).restore("run-A", "cp-A")
        self.assertEqual(self.states.load_execution_state("run-A"), self.execution)
        self.assertEqual(self.states.load_workflow_state("run-A"), self.workflow)
        self.assertEqual(self.states.load_loop_control_state("run-A", "loop-A"), self.loop)
        self.assertFalse(self.states.layout.loop_state("run-A", "later-loop").exists())
        self.assertEqual({path: path.read_bytes() for path in before_evidence}, before_evidence)
        self.assertEqual(self.evidence.verify_record("ev-later", expected_run_id="run-A")["evidence_id"], "ev-later")
        self.assertEqual(CheckpointStore(self.root).load("run-A", "cp-A"), checkpoint)

    def test_resume_blocks_changed_policy_and_issued_action_context(self):
        self.states.save_execution_state({**self.execution, "current_action_id": "issued-A", "active_tool_invocation_ref": "tool-A"})
        self.checkpoint()
        for field, blocker in (("policy_revision", "policy_revision_changed_without_compatibility"), ("context_revision", "issued_action_must_not_be_reused"), ("tool_schema_revision", "external_action_may_be_in_flight")):
            with self.subTest(field=field):
                decision = self.resume({**self.fingerprint, field: "v2"})
                self.assertFalse(decision["allowed"])
                self.assertIn(blocker, decision["blockers"])

    def test_safe_boundary_rematerializes_changed_context(self):
        self.checkpoint()
        decision = self.resume({**self.fingerprint, "context_revision": "v2"})
        self.assertEqual(decision["decision"], "resume_with_revalidation")
        self.assertEqual(decision["required_actions"], ["rematerialize_context"])

    def test_corrupt_snapshot_blocks_resume_and_restore_without_current_changes(self):
        checkpoint = self.checkpoint()
        (self.root / checkpoint["execution_state_ref"]).write_text('{"status":', encoding="utf-8")
        before = {path: path.read_bytes() for path in self.states.layout.run_root("run-A").joinpath("current").rglob("*") if path.is_file()}
        for operation in (self.resume, lambda: CheckpointStore(self.root).restore("run-A", "cp-A")):
            with self.subTest(operation=operation):
                with self.assertRaises(PersistenceError) as captured:
                    operation()
                self.assertEqual(captured.exception.code, "record_corrupt")
                self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_checkpoint_identity_and_hash_are_checked(self):
        checkpoint = self.checkpoint()
        path = self.states.layout.checkpoint("run-A", "cp-A")
        for changes, code in (({"run_id": "run-B"}, "checkpoint_identity_mismatch"), ({"reason": "tampered"}, "checkpoint_integrity_failed")):
            with self.subTest(changes=changes):
                atomic_write_json(path, {**checkpoint, **changes})
                with self.assertRaises(PersistenceError) as captured:
                    self.resume()
                self.assertEqual(captured.exception.code, code)

    def invalid_states(self):
        return [
            ("execution-state", {key: value for key, value in self.execution.items() if key != "status"}, "contract_missing_field"),
            ("workflow-state", {key: value for key, value in self.workflow.items() if key != "active_node_id"}, "contract_missing_field"),
            ("loop-control-state", {key: value for key, value in self.loop.items() if key != "decision"}, "contract_missing_field"),
            ("execution-state", {**self.execution, "status": "invalid"}, "invalid_execution_state"),
            ("workflow-state", {**self.workflow, "active_node_id": 17}, "invalid_workflow_state"),
            ("loop-control-state", {**self.loop, "decision": "invalid"}, "invalid_loop_control_state"),
            ("loop-control-state", {**self.loop, "semantic_attempt": True}, "invalid_loop_control_state"),
            ("loop-control-state", {**self.loop, "loop_id": "../escaped"}, "invalid_identifier"),
        ]

    def test_invalid_current_state_cannot_publish_checkpoint(self):
        paths = {"execution-state": self.states.layout.execution_state("run-A"), "workflow-state": self.states.layout.workflow_state("run-A"), "loop-control-state": self.states.layout.loop_state("run-A", "loop-A")}
        for index, (kind, invalid, code) in enumerate(self.invalid_states()):
            with self.subTest(kind=kind, invalid=invalid):
                path = paths[kind]
                original = path.read_bytes()
                try:
                    atomic_write_json(path, invalid)
                    before = {item: item.read_bytes() for item in self.states.layout.run_root("run-A").joinpath("current").rglob("*") if item.is_file()}
                    with self.assertRaises(PersistenceError) as captured:
                        self.checkpoint(checkpoint_id=f"invalid-{index}")
                    self.assertEqual(captured.exception.code, code)
                    self.assertFalse(self.states.layout.checkpoint("run-A", f"invalid-{index}").exists())
                    self.assertEqual({item: item.read_bytes() for item in before}, before)
                finally:
                    path.write_bytes(original)

    def test_schema_invalid_snapshot_blocks_resume_and_restore_without_changes(self):
        checkpoint = self.checkpoint()
        checkpoint_path = self.states.layout.checkpoint("run-A", "cp-A")
        refs = {"execution-state": checkpoint["execution_state_ref"], "workflow-state": checkpoint["workflow_state_ref"], "loop-control-state": checkpoint["loop_control_state_refs"][0]}
        self.states.save_execution_state({**self.execution, "status": "failed"})
        self.states.save_loop_control_state({**self.loop, "loop_id": "later-loop"})
        current = self.states.layout.run_root("run-A") / "current"
        before = {item.relative_to(current).as_posix(): item.read_bytes() for item in current.rglob("*") if item.is_file()}
        for kind, invalid, code in self.invalid_states():
            with self.subTest(kind=kind, invalid=invalid):
                path = self.root / refs[kind]
                original = path.read_bytes()
                try:
                    candidate = deepcopy(checkpoint)
                    atomic_write_json(path, invalid)
                    if kind == "loop-control-state":
                        candidate["state_snapshot_hashes"]["loop_control_states"] = {invalid.get("loop_id", "loop-A"): sha256_json(invalid)}
                    else:
                        candidate["state_snapshot_hashes"][kind.replace("-", "_")] = sha256_json(invalid)
                    candidate["checkpoint_hash"] = sha256_json({key: value for key, value in candidate.items() if key != "checkpoint_hash"})
                    atomic_write_json(checkpoint_path, candidate)
                    # Hashは成立させ、State契約の拒否と全Current保護を独立して確認する。
                    for operation in (self.resume, lambda: CheckpointStore(self.root).restore("run-A", "cp-A")):
                        with self.assertRaises(PersistenceError) as captured:
                            operation()
                        self.assertEqual(captured.exception.code, code)
                        self.assertEqual({item.relative_to(current).as_posix(): item.read_bytes() for item in current.rglob("*") if item.is_file()}, before)
                finally:
                    path.write_bytes(original)
                    atomic_write_json(checkpoint_path, checkpoint)

    def test_explicit_child_run_evidence_union_survives_checkpoint_and_restore(self):
        self.evidence.append(evidence_record(evidence_id="ev-B", run_id="run-B"))
        # Task DAGの親Checkpointは、明示された子RunのEvidence unionを保持する契約。
        self.checkpoint(evidence_refs=["ev-A", "ev-B"])
        self.assertEqual(self.resume()["decision"], "resume")
        CheckpointStore(self.root).restore("run-A", "cp-A")
        self.assertEqual(self.evidence.verify_record("ev-B", expected_run_id="run-B")["evidence_id"], "ev-B")

    def test_tampered_evidence_blocks_resume_and_restore(self):
        self.checkpoint()
        path = self.evidence.layout.evidence("ev-A")
        atomic_write_json(path, {**read_json(path), "verification_status": "failed"})
        for operation in (self.resume, lambda: CheckpointStore(self.root).restore("run-A", "cp-A")):
            with self.subTest(operation=operation):
                with self.assertRaises(PersistenceError) as captured:
                    operation()
                self.assertEqual(captured.exception.code, "evidence_tampered")
                self.assertEqual(self.states.load_execution_state("run-A"), self.execution)

    def test_tampered_evidence_prevents_checkpoint_creation(self):
        path = self.evidence.layout.evidence("ev-A")
        atomic_write_json(path, {**read_json(path), "verification_status": "failed"})
        with self.assertRaises(PersistenceError) as captured:
            self.checkpoint()
        self.assertEqual(captured.exception.code, "evidence_tampered")
        self.assertFalse(self.states.layout.checkpoint("run-A", "cp-A").exists())

    def test_foreign_snapshot_with_valid_hash_cannot_overwrite_other_run(self):
        checkpoint = deepcopy(self.checkpoint())
        foreign = {**self.execution, "run_id": "run-B", "status": "failed"}
        self.states.save_execution_state(foreign)
        foreign_path = self.states.layout.execution_state("run-B")
        checkpoint["execution_state_ref"] = foreign_path.relative_to(self.root).as_posix()
        checkpoint["state_snapshot_hashes"]["execution_state"] = sha256_json(foreign)
        checkpoint["checkpoint_hash"] = sha256_json({key: value for key, value in checkpoint.items() if key != "checkpoint_hash"})
        atomic_write_json(self.states.layout.checkpoint("run-A", "cp-A"), checkpoint)
        with self.assertRaises(PersistenceError) as captured:
            CheckpointStore(self.root).restore("run-A", "cp-A")
        self.assertEqual(captured.exception.code, "state_identity_mismatch")
        self.assertEqual(self.states.load_execution_state("run-B"), foreign)
        self.assertEqual(self.states.load_execution_state("run-A"), self.execution)

    def test_abrupt_exit_before_atomic_replace_preserves_recoverable_checkpoint(self):
        self.checkpoint()
        path = self.states.layout.execution_state("run-A")
        original = path.read_bytes()
        code = """import os, sys
from pathlib import Path
from unittest.mock import patch
from unityagent.persistence.store.atomic_store import atomic_write_json
with patch('unityagent.persistence.store.atomic_store.os.replace', side_effect=lambda *args: os._exit(73)):
    atomic_write_json(Path(sys.argv[1]), {'partial': True})
"""
        child = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, timeout=20)
        self.assertEqual(child.returncode, 73, child.stderr.decode(errors="replace"))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.resume()["decision"], "resume")
        CheckpointStore(self.root).restore("run-A", "cp-A")
        self.assertEqual(self.states.load_execution_state("run-A"), self.execution)

    def test_interrupted_task_run_is_not_redispatched_on_resume(self):
        project = self.root / "project"
        for name in ("Assets", "Packages", "ProjectSettings"):
            (project / name).mkdir(parents=True)
        tasks = [{"id": "inspect", "workspace": str(project), "goal": "Inspect test project", "required_gates": {"inspection": ["project_fact"]}, "entry_request": {"schema_version": "2.0", "request_id": "request-A", "entry_point": "codex_plugin", "project_root": str(project), "intent": {"kind": "project_inspection"}}}]
        plane = UnityAgentControlPlane(self.root)
        parameters = {"tasks": tasks, "run_id": "dag-A", "definition_fingerprint": self.fingerprint, "task_parameters": {"inspect": {}}}
        # 子実行が返らず終了した境界を注入し、親の実StateとResume判定を検証する。
        with patch.object(plane, "execute", side_effect=SystemExit("interrupted")) as dispatch:
            with self.assertRaisesRegex(SystemExit, "interrupted"):
                plane.execute_tasks(**parameters)
            dispatch.assert_called_once()
        before = plane.state_store.layout.run_root("dag-A").joinpath("current/task-state.json").read_bytes()
        self.assertEqual(plane.state_store.load_task_state("dag-A")["tasks"]["inspect"]["status"], "running")
        recovered = UnityAgentControlPlane(self.root)
        with patch.object(recovered, "execute") as dispatch:
            with self.assertRaisesRegex(ValueError, "Uncertain external side effects"):
                recovered.execute_tasks(**parameters, resume=True)
            dispatch.assert_not_called()
        self.assertEqual(plane.state_store.layout.run_root("dag-A").joinpath("current/task-state.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
