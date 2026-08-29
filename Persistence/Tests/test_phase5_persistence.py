import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from Context.Retrieval.Memory.project_memory import retrieve_projections
from Orchestration.Graph.state_mapping import loop_control_state_patch, workflow_state_patch
from Persistence.Checkpoint.checkpoint_store import CheckpointStore
from Persistence.Compatibility.legacy_graph_loader import normalize_legacy_run_state, reject_continuation_decision_as_durable_state
from Persistence.Compatibility.legacy_memory_loader import normalize_legacy_layered_records
from Persistence.Evidence.evidence_store import EvidenceStore
from Persistence.Evidence.runtime_adapter import from_runtime_execution_evidence
from Persistence.Memory.memory_store import MemoryStore
from Persistence.Migrations.checkpoint_migrations import migrate_v1_0_to_v1_1
from Persistence.Resume.resume import evaluate_resume
from Persistence.Session.session_store import SessionStore
from Persistence.State.state_store import StateStore
from Persistence.Store.atomic_store import PersistenceError, read_json, sha256_json, write_immutable_json


def fingerprint(**overrides):
    value = {
        "schema_version": "1.0",
        "architecture_version": "3.1",
        "policy_revision": "policy-a",
        "prompt_revision": "prompt-a",
        "context_revision": "context-a",
        "graph_revision": "graph-a",
        "runtime_profile_revision": "runtime-a",
        "tool_schema_revision": "tools-a",
        "checkpoint_schema_revision": "1.1",
        "evidence_schema_revision": "1.1",
        "eval_contract_revision": "eval-a",
    }
    value.update(overrides)
    return value


def execution_state(run_id="run-1", **overrides):
    value = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "running",
        "current_step_id": "inspect_sources",
        "current_action_id": None,
        "active_tool_invocation_ref": None,
        "evidence_refs": [],
        "updated_at": "2026-08-29T00:00:00Z",
    }
    value.update(overrides)
    return value


class Phase5PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.states = StateStore(self.root)
        self.states.save_execution_state(execution_state())
        self.states.save_workflow_state(workflow_state_patch(
            run_id="run-1", parent_graph_id="development",
            active_subgraph_id="investigation", active_node_id="inspect_sources",
            updated_at="2026-08-29T00:00:00Z",
        ))
        self.states.save_loop_control_state(loop_control_state_patch(
            run_id="run-1", loop_id="investigation-evidence-loop",
            semantic_attempt=1, progress_marker="source-read",
            decision="continue", updated_at="2026-08-29T00:00:00Z",
        ))

    def tearDown(self):
        self.temp.cleanup()

    def test_one_authoritative_execution_state_path(self):
        path = self.states.layout.execution_state("run-1")
        self.assertEqual(path.relative_to(self.root).as_posix(), "runs/run-1/current/execution-state.json")
        self.assertEqual(self.states.load_execution_state("run-1")["run_id"], "run-1")

    def test_checkpoint_snapshots_are_immutable_and_distinct_from_current_state(self):
        checkpoint = CheckpointStore(self.root).create(
            checkpoint_id="cp-1", run_id="run-1", reason="before mutation",
            loop_ids=["investigation-evidence-loop"], evidence_refs=[],
            definition_fingerprint=fingerprint(), created_at="2026-08-29T00:01:00Z",
        )
        self.assertNotIn("/current/", "/" + checkpoint["execution_state_ref"])
        snapshot = read_json(self.root / checkpoint["execution_state_ref"])
        self.assertEqual(snapshot["current_step_id"], "inspect_sources")
        self.states.save_execution_state(execution_state(current_step_id="execute_change", updated_at="2026-08-29T00:02:00Z"))
        self.assertEqual(read_json(self.root / checkpoint["execution_state_ref"])["current_step_id"], "inspect_sources")
        self.assertEqual(self.states.load_execution_state("run-1")["current_step_id"], "execute_change")

    def test_checkpoint_tamper_fails_closed(self):
        store = CheckpointStore(self.root)
        store.create(
            checkpoint_id="cp-tamper", run_id="run-1", reason="test",
            loop_ids=[], evidence_refs=[], definition_fingerprint=fingerprint(),
            created_at="2026-08-29T00:01:00Z",
        )
        path = store.layout.checkpoint("run-1", "cp-tamper")
        value = read_json(path)
        value["reason"] = "tampered"
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(PersistenceError) as ctx:
            store.load("run-1", "cp-tamper")
        self.assertEqual(ctx.exception.code, "checkpoint_integrity_failed")

    def test_evidence_is_append_immutable_and_runtime_adapter_is_lossless(self):
        runtime = {
            "schema_version": "1.0", "evidence_id": "ev-1", "run_id": "run-1",
            "step_id": "verify", "producer": "runtime", "source_type": "test",
            "source_ref": "artifact://result", "status": "passed",
            "payload_ref": "Artifacts/result.json", "hash": "sha256:" + "a" * 64,
            "timestamp": "2026-08-29T00:00:00Z", "provenance": ["runtime:test"],
            "gate_outcome": {"gate_id": "compile", "status": "passed"},
            "definition_fingerprint": fingerprint(),
        }
        durable = from_runtime_execution_evidence(runtime)
        self.assertEqual(durable["verification_status"], "passed")
        self.assertEqual(durable["gate_outcome"], runtime["gate_outcome"])
        store = EvidenceStore(self.root)
        self.assertTrue(store.append(durable))
        self.assertFalse(store.append(durable))
        changed = deepcopy(durable)
        changed["verification_status"] = "failed"
        with self.assertRaises(PersistenceError) as ctx:
            store.append(changed)
        self.assertEqual(ctx.exception.code, "immutable_record_conflict")

    def test_memory_is_immutable_scoped_and_promotion_never_writes_policy(self):
        record = {
            "schema_version": "1.1", "memory_id": "mem-1", "statement": "URP validation requires runtime evidence",
            "scope_class": "project_internal", "confidence": "verified",
            "source_evidence_refs": ["ev-1"], "source_memory_refs": [],
            "created_at": "2026-08-29T00:00:00Z", "updated_at": "2026-08-29T00:00:00Z",
            "applicability": ["Unity"], "limits": [], "layer": "reusable_candidate",
            "provenance": ["ev-1"], "promotion_target": "user_policy_candidate",
            "review_status": "approved", "supersedes": [], "conflicts_with": [],
            "repository": None, "unity_version": None, "platform": None, "tags": ["urp"],
        }
        store = MemoryStore(self.root)
        self.assertTrue(store.put(record))
        self.assertEqual(store.list_accessible("generic_planning"), [])
        blocked = store.promote("mem-1", "user_policy_candidate", human_gate_approved=False)
        self.assertFalse(blocked["approved"])
        approved = store.promote("mem-1", "user_policy_candidate", human_gate_approved=True)
        self.assertTrue(approved["approved"])
        self.assertFalse(approved["writes_external_authority"])
        changed = deepcopy(record)
        changed["statement"] = "different"
        with self.assertRaises(PersistenceError):
            store.put(changed)

    def test_context_memory_projection_is_read_only(self):
        store = MemoryStore(self.root)
        store.put({
            "schema_version": "1.1", "memory_id": "mem-safe", "statement": "Shader variants need platform evidence",
            "scope_class": "portable_artifact", "confidence": "verified", "source_evidence_refs": ["ev-1"],
            "created_at": "2026-08-29T00:00:00Z", "updated_at": "2026-08-29T00:00:00Z",
            "applicability": ["shader"], "limits": [],
        })
        before = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*") if path.is_file())
        result = retrieve_projections(
            store_root=self.root, query="shader platform", execution_profile="generic_planning",
            selected_at="2026-08-29T00:00:01Z",
        )
        after = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*") if path.is_file())
        self.assertEqual(before, after)
        self.assertEqual(result["items"][0]["projection"]["memory_id"], "mem-safe")
        self.assertEqual(result["items"][0]["projection"]["source_evidence_refs"], ["ev-1"])
        self.assertFalse(result["raw_content_included"])

    def _checkpoint(self, fp=None):
        return CheckpointStore(self.root).create(
            checkpoint_id="resume-cp", run_id="run-1", reason="resume",
            loop_ids=["investigation-evidence-loop"], evidence_refs=[],
            definition_fingerprint=fp or fingerprint(), created_at="2026-08-29T00:01:00Z",
        )

    def test_identical_fingerprint_resumes(self):
        self._checkpoint()
        decision = evaluate_resume(
            store_root=self.root, run_id="run-1", checkpoint_id="resume-cp",
            current_definition_fingerprint=fingerprint(),
        )
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["decision"], "resume")

    def test_policy_change_fails_closed_without_explicit_compatibility(self):
        self._checkpoint()
        decision = evaluate_resume(
            store_root=self.root, run_id="run-1", checkpoint_id="resume-cp",
            current_definition_fingerprint=fingerprint(policy_revision="policy-b"),
        )
        self.assertFalse(decision["allowed"])
        self.assertIn("policy_revision_changed_without_compatibility", decision["blockers"])

    def test_context_change_before_issued_action_requires_rematerialization(self):
        self._checkpoint()
        decision = evaluate_resume(
            store_root=self.root, run_id="run-1", checkpoint_id="resume-cp",
            current_definition_fingerprint=fingerprint(context_revision="context-b"),
        )
        self.assertTrue(decision["allowed"])
        self.assertIn("rematerialize_context", decision["required_actions"])

    def test_tool_change_with_inflight_action_blocks_resume(self):
        self.states.save_execution_state(execution_state(active_tool_invocation_ref="tool-call-1"))
        self._checkpoint()
        decision = evaluate_resume(
            store_root=self.root, run_id="run-1", checkpoint_id="resume-cp",
            current_definition_fingerprint=fingerprint(tool_schema_revision="tools-b"),
        )
        self.assertFalse(decision["allowed"])
        self.assertIn("external_action_may_be_in_flight", decision["blockers"])

    def test_v1_checkpoint_migration_creates_copy_and_preserves_original(self):
        refs, _ = self.states.snapshot_run("run-1", [])
        source = {
            "schema_version": "1.0", "checkpoint_id": "legacy-cp", "run_id": "run-1",
            "created_at": "2026-08-29T00:00:00Z", "reason": "legacy",
            "execution_state_ref": refs["execution_state"], "workflow_state_ref": refs["workflow_state"],
            "loop_control_state_refs": [], "evidence_refs": [], "definition_fingerprint": fingerprint(checkpoint_schema_revision="1.0"),
        }
        write_immutable_json(self.states.layout.checkpoint("run-1", "legacy-cp"), source)
        migrated = migrate_v1_0_to_v1_1(
            store_root=self.root, run_id="run-1", source_checkpoint_id="legacy-cp",
            new_checkpoint_id="migrated-cp", current_definition_fingerprint=fingerprint(),
        )
        self.assertEqual(read_json(self.states.layout.checkpoint("run-1", "legacy-cp"))["schema_version"], "1.0")
        self.assertEqual(migrated["schema_version"], "1.1")
        self.assertEqual(migrated["migration_from"]["checkpoint_id"], "legacy-cp")
        CheckpointStore(self.root).load("run-1", "migrated-cp")

    def test_legacy_graph_loader_requires_exact_topology_mapping(self):
        legacy = {
            "run_id": "legacy-run", "status": "running", "updated_at": "2026-08-29T00:00:00Z",
            "nodes": [{"id": "inspect_sources", "status": "running", "attempts": 2, "last_action": "read", "last_evidence": ["ev-1"]}],
        }
        normalized = normalize_legacy_run_state(
            legacy, parent_graph_id="development", subgraph_by_node={"inspect_sources": "investigation"},
        )
        self.assertEqual(normalized["workflow_state"]["active_subgraph_id"], "investigation")
        self.assertEqual(normalized["loop_control_states"], [])
        with self.assertRaises(PersistenceError):
            normalize_legacy_run_state(legacy, parent_graph_id="development", subgraph_by_node={})
        with self.assertRaises(PersistenceError):
            reject_continuation_decision_as_durable_state({"controller": "native_continuation"})

    def test_legacy_layered_memory_splits_raw_evidence_from_memory(self):
        legacy = [
            {
                "memory_id": "ev-legacy", "layer": "L0_raw_evidence", "statement": "raw",
                "raw_refs": ["Evidence/raw/ev-legacy.txt"], "confidence": "verified",
                "scope_class": "portable_artifact", "sha256": "b" * 64,
            },
            {
                "memory_id": "atom-1", "layer": "L1_atom", "statement": "observation",
                "raw_refs": ["Evidence/raw/ev-legacy.txt"], "confidence": "verified",
                "scope_class": "portable_artifact", "created_at": "2026-08-29T00:00:00Z",
            },
            {
                "memory_id": "scenario-1", "layer": "L2_scenario", "statement": "scenario",
                "atom_refs": ["atom-1"], "confidence": "probable", "scope_class": "portable_artifact",
                "created_at": "2026-08-29T00:00:00Z", "applicability": ["Unity"], "limits": ["one case"],
            },
        ]
        result = normalize_legacy_layered_records(legacy)
        self.assertEqual([x["evidence_id"] for x in result["evidence_candidates"]], ["ev-legacy"])
        records = {x["memory_id"]: x for x in result["memory_records"]}
        self.assertEqual(records["atom-1"]["source_evidence_refs"], ["ev-legacy"])
        self.assertIn("atom-1", records["scenario-1"]["source_memory_refs"])
        self.assertEqual(records["scenario-1"]["source_evidence_refs"], ["ev-legacy"])

    def test_memory_scope_downgrade_is_blocked(self):
        store = MemoryStore(self.root)
        store.put({
            "schema_version": "1.1", "memory_id": "internal-parent", "statement": "internal",
            "scope_class": "project_internal", "confidence": "verified", "source_evidence_refs": ["ev-1"],
            "created_at": "2026-08-29T00:00:00Z", "updated_at": "2026-08-29T00:00:00Z",
            "applicability": [], "limits": [],
        })
        with self.assertRaises(PersistenceError) as ctx:
            store.put({
                "schema_version": "1.1", "memory_id": "unsafe-child", "statement": "derived",
                "scope_class": "portable_artifact", "confidence": "verified", "source_evidence_refs": ["ev-1"],
                "source_memory_refs": ["internal-parent"],
                "created_at": "2026-08-29T00:00:00Z", "updated_at": "2026-08-29T00:00:00Z",
                "applicability": [], "limits": [],
            })
        self.assertEqual(ctx.exception.code, "memory_scope_downgrade_forbidden")

    def test_checkpoint_restore_restores_only_state_records(self):
        checkpoints = CheckpointStore(self.root)
        checkpoints.create(
            checkpoint_id="restore-cp", run_id="run-1", reason="restore",
            loop_ids=["investigation-evidence-loop"], evidence_refs=[],
            definition_fingerprint=fingerprint(), created_at="2026-08-29T00:01:00Z",
        )
        self.states.save_execution_state(
            execution_state(current_step_id="execute_change", updated_at="2026-08-29T00:02:00Z")
        )
        checkpoints.restore("run-1", "restore-cp")
        self.assertEqual(self.states.load_execution_state("run-1")["current_step_id"], "inspect_sources")

    def test_session_record_is_distinct_from_checkpoint(self):
        sessions = SessionStore(self.root)
        sessions.save({
            "schema_version": "1.0", "session_id": "session-1",
            "created_at": "2026-08-29T00:00:00Z", "updated_at": "2026-08-29T00:00:00Z",
            "active_run_ids": ["run-1"], "last_checkpoint_ref": None, "metadata": {"surface": "test"},
        })
        path = sessions.layout.session("session-1")
        self.assertEqual(path.relative_to(self.root).as_posix(), "sessions/session-1.json")
        self.assertNotIn("checkpoints", path.as_posix())

    def test_explicit_compatible_policy_change_still_requires_policy_revalidation(self):
        self._checkpoint()
        decision = evaluate_resume(
            store_root=self.root, run_id="run-1", checkpoint_id="resume-cp",
            current_definition_fingerprint=fingerprint(policy_revision="policy-b"),
            compatibility={"policy_compatible_pairs": [["policy-a", "policy-b"]]},
        )
        self.assertTrue(decision["allowed"])
        self.assertIn("revalidate_policy_and_approval", decision["required_actions"])

    def test_legacy_checkpoint_with_mutable_current_refs_cannot_be_migrated(self):
        source = {
            "schema_version": "1.0", "checkpoint_id": "unsafe-legacy", "run_id": "run-1",
            "created_at": "2026-08-29T00:00:00Z", "reason": "legacy",
            "execution_state_ref": "runs/run-1/current/execution-state.json",
            "workflow_state_ref": "runs/run-1/current/workflow-state.json",
            "loop_control_state_refs": [], "evidence_refs": [],
            "definition_fingerprint": fingerprint(checkpoint_schema_revision="1.0"),
        }
        write_immutable_json(self.states.layout.checkpoint("run-1", "unsafe-legacy"), source)
        with self.assertRaises(PersistenceError) as ctx:
            migrate_v1_0_to_v1_1(
                store_root=self.root, run_id="run-1", source_checkpoint_id="unsafe-legacy",
                new_checkpoint_id="should-not-exist", current_definition_fingerprint=fingerprint(),
            )
        self.assertEqual(ctx.exception.code, "legacy_checkpoint_mutable_ref_unsafe")

    def test_checkpoint_rejects_non_durable_evidence_reference(self):
        with self.assertRaises(PersistenceError) as ctx:
            CheckpointStore(self.root).create(
                checkpoint_id="bad-evidence-cp", run_id="run-1", reason="bad ref",
                loop_ids=[], evidence_refs=["captured-but-not-appended"],
                definition_fingerprint=fingerprint(), created_at="2026-08-29T00:01:00Z",
            )
        self.assertEqual(ctx.exception.code, "record_not_found")

    def test_persistence_implementation_does_not_import_runtime_or_orchestration(self):
        root = Path(__file__).resolve().parents[2] / "Persistence"
        implementation = []
        for folder in ("Store", "State", "Evidence", "Memory", "Session", "Checkpoint", "Resume", "Migrations", "Compatibility"):
            implementation.extend((root / folder).glob("*.py"))
        text = "\n".join(path.read_text(encoding="utf-8") for path in implementation)
        self.assertNotRegex(text, r"(?m)^\s*(?:from|import)\s+Runtime\b")
        self.assertNotRegex(text, r"(?m)^\s*(?:from|import)\s+Orchestration\b")


if __name__ == "__main__":
    unittest.main()
