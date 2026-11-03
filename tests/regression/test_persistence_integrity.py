"""Persistenceの実保存・不変レコード・Evidence改竄検出を検証する。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from unityagent.persistence.contracts.definition_fingerprint import DEFINITION_FIELDS
from unityagent.persistence.evidence.evidence_store import EvidenceStore
from unityagent.persistence.state.state_store import StateStore
from unityagent.persistence.store.atomic_store import (
    PersistenceError,
    atomic_write_json,
    read_json,
    resolve_ref,
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
        "provenance": {"test_source": "regression"},
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

    def test_event_chain_corruption_is_detected(self):
        store = EvidenceStore(self.root)
        store.append(evidence_record(evidence_id="evidence-A", run_id="run-A"))
        events = store.layout.evidence_events("run-A")
        contents = events.read_text(encoding="utf-8")
        events.write_text(contents.replace('"previous_event_hash":null', '"previous_event_hash":"sha256:wrong"'), encoding="utf-8")
        self.assertNotEqual(events.read_text(encoding="utf-8"), contents)

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


if __name__ == "__main__":
    unittest.main()
