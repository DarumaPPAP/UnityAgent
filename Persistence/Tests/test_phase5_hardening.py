import tempfile
import unittest
from pathlib import Path

from Orchestration.Graph.state_mapping import loop_control_state_patch, workflow_state_patch
from Persistence.Checkpoint.checkpoint_store import CheckpointStore
from Persistence.Evidence.evidence_store import EvidenceStore
from Persistence.Migrations.checkpoint_migrations import migrate_v1_0_to_v1_1
from Persistence.State.state_store import StateStore
from Persistence.Store.atomic_store import PersistenceError, write_immutable_json


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


def execution_state(run_id="run-1", step="inspect_sources"):
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "running",
        "current_step_id": step,
        "current_action_id": None,
        "active_tool_invocation_ref": None,
        "evidence_refs": [],
        "updated_at": "2026-08-29T00:00:00Z",
    }


class Phase5PersistenceHardeningTests(unittest.TestCase):
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
            run_id="run-1", loop_id="checkpoint-loop", semantic_attempt=1,
            progress_marker="before", decision="continue", updated_at="2026-08-29T00:00:00Z",
        ))

    def tearDown(self):
        self.temp.cleanup()

    def test_checkpoint_rejects_incomplete_definition_fingerprint(self):
        bad = fingerprint()
        bad.pop("graph_revision")
        with self.assertRaises(PersistenceError) as ctx:
            CheckpointStore(self.root).create(
                checkpoint_id="bad-fp", run_id="run-1", reason="test",
                loop_ids=[], evidence_refs=[], definition_fingerprint=bad,
                created_at="2026-08-29T00:01:00Z",
            )
        self.assertEqual(ctx.exception.code, "invalid_definition_fingerprint")

    def test_evidence_rejects_incomplete_definition_fingerprint(self):
        bad = fingerprint()
        bad["tool_schema_revision"] = ""
        record = {
            "schema_version": "1.1", "evidence_id": "ev-bad", "run_id": "run-1",
            "step_id": "verify", "source_type": "test", "source_ref": None,
            "timestamp": "2026-08-29T00:00:00Z", "hash": None,
            "producer": "runtime", "verification_status": "unavailable",
            "provenance": ["runtime:test"], "payload_ref": None,
            "gate_outcome": None, "definition_fingerprint": bad,
        }
        with self.assertRaises(PersistenceError) as ctx:
            EvidenceStore(self.root).append(record)
        self.assertEqual(ctx.exception.code, "invalid_definition_fingerprint")

    def test_restore_removes_loop_state_created_after_checkpoint(self):
        checkpoints = CheckpointStore(self.root)
        checkpoints.create(
            checkpoint_id="exact-state", run_id="run-1", reason="test",
            loop_ids=["checkpoint-loop"], evidence_refs=[], definition_fingerprint=fingerprint(),
            created_at="2026-08-29T00:01:00Z",
        )
        self.states.save_loop_control_state(loop_control_state_patch(
            run_id="run-1", loop_id="later-loop", semantic_attempt=1,
            progress_marker="later", decision="continue", updated_at="2026-08-29T00:02:00Z",
        ))
        self.states.save_execution_state(execution_state(step="execute_change"))
        checkpoints.restore("run-1", "exact-state")
        self.assertEqual(self.states.load_execution_state("run-1")["current_step_id"], "inspect_sources")
        self.assertFalse(self.states.layout.loop_state("run-1", "later-loop").exists())
        self.assertTrue(self.states.layout.loop_state("run-1", "checkpoint-loop").exists())

    def test_checkpoint_schema_migration_cannot_launder_graph_revision(self):
        refs, _ = self.states.snapshot_run("run-1", [])
        source = {
            "schema_version": "1.0", "checkpoint_id": "legacy", "run_id": "run-1",
            "created_at": "2026-08-29T00:00:00Z", "reason": "legacy",
            "execution_state_ref": refs["execution_state"],
            "workflow_state_ref": refs["workflow_state"],
            "loop_control_state_refs": [], "evidence_refs": [],
            "definition_fingerprint": fingerprint(checkpoint_schema_revision="1.0"),
        }
        write_immutable_json(self.states.layout.checkpoint("run-1", "legacy"), source)
        with self.assertRaises(PersistenceError) as ctx:
            migrate_v1_0_to_v1_1(
                store_root=self.root, run_id="run-1", source_checkpoint_id="legacy",
                new_checkpoint_id="laundered", current_definition_fingerprint=fingerprint(graph_revision="graph-b"),
            )
        self.assertEqual(ctx.exception.code, "migration_definition_laundering_forbidden")
        self.assertFalse(self.states.layout.checkpoint("run-1", "laundered").exists())

    def test_checkpoint_schema_migration_preserves_semantic_fingerprint(self):
        refs, _ = self.states.snapshot_run("run-1", [])
        source_fp = fingerprint(checkpoint_schema_revision="1.0")
        source = {
            "schema_version": "1.0", "checkpoint_id": "legacy-ok", "run_id": "run-1",
            "created_at": "2026-08-29T00:00:00Z", "reason": "legacy",
            "execution_state_ref": refs["execution_state"],
            "workflow_state_ref": refs["workflow_state"],
            "loop_control_state_refs": [], "evidence_refs": [],
            "definition_fingerprint": source_fp,
        }
        write_immutable_json(self.states.layout.checkpoint("run-1", "legacy-ok"), source)
        migrated = migrate_v1_0_to_v1_1(
            store_root=self.root, run_id="run-1", source_checkpoint_id="legacy-ok",
            new_checkpoint_id="migrated-ok", current_definition_fingerprint=fingerprint(),
        )
        self.assertEqual(migrated["definition_fingerprint"]["graph_revision"], "graph-a")
        self.assertEqual(migrated["definition_fingerprint"]["policy_revision"], "policy-a")
        self.assertEqual(migrated["definition_fingerprint"]["checkpoint_schema_revision"], "1.1")

    def test_checkpoint_verification_requires_referenced_durable_evidence(self):
        evidence = {
            "schema_version": "1.1", "evidence_id": "ev-1", "run_id": "run-1",
            "step_id": "verify", "source_type": "test", "source_ref": None,
            "timestamp": "2026-08-29T00:00:00Z", "hash": None,
            "producer": "runtime", "verification_status": "passed",
            "provenance": ["runtime:test"], "payload_ref": None,
            "gate_outcome": None, "definition_fingerprint": fingerprint(),
        }
        evidence_store = EvidenceStore(self.root)
        evidence_store.append(evidence)
        checkpoint_store = CheckpointStore(self.root)
        checkpoint_store.create(
            checkpoint_id="with-evidence", run_id="run-1", reason="test",
            loop_ids=[], evidence_refs=["ev-1"], definition_fingerprint=fingerprint(),
            created_at="2026-08-29T00:01:00Z",
        )
        evidence_store.layout.evidence("ev-1").unlink()
        with self.assertRaises(PersistenceError) as ctx:
            checkpoint_store.load("run-1", "with-evidence", verify=True)
        self.assertEqual(ctx.exception.code, "record_not_found")


if __name__ == "__main__":
    unittest.main()
