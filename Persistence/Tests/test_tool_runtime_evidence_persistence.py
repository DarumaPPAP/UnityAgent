from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Persistence.Evidence.evidence_store import EvidenceStore
from Persistence.Evidence.runtime_adapter import (
    append_runtime_execution_evidence,
    from_runtime_execution_evidence,
)
from Persistence.Store.atomic_store import PersistenceError


class ToolRuntimeEvidencePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fingerprint(self):
        return {
            "schema_version": "1.0",
            "architecture_version": "arch",
            "policy_revision": "policy",
            "prompt_revision": "prompt",
            "context_revision": "context",
            "graph_revision": "graph",
            "runtime_profile_revision": "runtime",
            "tool_schema_revision": "tools",
            "checkpoint_schema_revision": "checkpoint",
            "evidence_schema_revision": "1.2",
            "eval_contract_revision": "1.2",
        }

    def runtime_v11(self):
        return {
            "schema_version": "1.1",
            "evidence_id": "evidence-1",
            "run_id": "run-1",
            "step_id": "step-1",
            "producer": "tool_runtime",
            "source_type": "provider_result",
            "source_ref": "artifact://structured/result.json",
            "status": "passed",
            "payload_ref": "artifact://structured/result.json",
            "hash": "sha256:abc",
            "timestamp": "2026-09-01T09:00:00+00:00",
            "provenance": ["provider:player_runtime", "capability:player.observe"],
            "gate_outcome": None,
            "definition_fingerprint": self.fingerprint(),
            "capability": "player.observe",
            "provider_ref": "player_runtime",
            "project_root": "/Project",
            "environment": {
                "profile_hint": "FULL",
                "binding_fingerprint": "a" * 64,
                "unity_version": "6000.3.15f1",
                "requested_target": "Switch",
            },
            "target": {
                "surface": "player",
                "instance_id": "player-1",
                "device_id": "switch-devkit-1",
                "artifact_id": "artifact-1",
                "command_ref": "observe.frame",
            },
            "safety_strength": 4,
            "evidence_strength": 4,
            "completion": "verified",
            "observation_state": "observed",
            "failure_class": None,
            "observed_evidence": ["player_observation"],
            "required_evidence": ["player_observation"],
            "raw_refs": ["artifact://raw/frame.json"],
            "mutation_provenance": None,
            "latency_ms": 3.5,
            "fallback_from": None,
            "durability": "current_run",
        }

    def legacy_runtime(self):
        return {
            "evidence_id": "legacy-evidence",
            "run_id": "run-1",
            "step_id": "step-1",
            "producer": "runtime",
            "source_type": "test",
            "source_ref": None,
            "status": "passed",
            "payload_ref": None,
            "hash": None,
            "timestamp": "2026-09-01T09:00:00+00:00",
            "provenance": ["legacy:test"],
            "gate_outcome": None,
            "definition_fingerprint": self.fingerprint(),
        }

    def validate_persistence_contract(self, schema_id, value):
        paths = list(ROOT.glob("**/Contracts/*.schema.yaml"))
        schemas = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]
        store = {schema["$id"]: schema for schema in schemas}
        schema = store[schema_id]
        Draft202012Validator(
            schema,
            resolver=RefResolver.from_schema(schema, store=store),
        ).validate(value)

    def test_conversion_preserves_provider_capability_environment_and_strength(self):
        durable = from_runtime_execution_evidence(self.runtime_v11())
        self.assertEqual(durable["schema_version"], "1.2")
        self.assertEqual(durable["provider_ref"], "player_runtime")
        self.assertEqual(durable["capability"], "player.observe")
        self.assertEqual(durable["environment"]["requested_target"], "Switch")
        self.assertEqual(durable["safety_strength"], 4)
        self.assertEqual(durable["evidence_strength"], 4)
        self.assertEqual(durable["durability"], "durable")
        self.validate_persistence_contract("urn:unityagent:persistence:evidence-record", durable)

    def test_conversion_alone_does_not_create_durable_record(self):
        durable = from_runtime_execution_evidence(self.runtime_v11())
        self.assertEqual(durable["durability"], "durable")
        store = EvidenceStore(self.root)
        with self.assertRaises(PersistenceError) as context:
            store.get("evidence-1")
        self.assertEqual(context.exception.code, "record_not_found")

    def test_append_is_the_durable_boundary_and_is_idempotent(self):
        store = EvidenceStore(self.root)
        first = append_runtime_execution_evidence(store, self.runtime_v11())
        self.assertTrue(first["durable"])
        self.assertTrue(first["created"])
        second = append_runtime_execution_evidence(store, self.runtime_v11())
        self.assertTrue(second["durable"])
        self.assertFalse(second["created"])
        self.assertEqual(second["record"], first["record"])

    def test_immutable_evidence_id_cannot_be_rewritten(self):
        store = EvidenceStore(self.root)
        append_runtime_execution_evidence(store, self.runtime_v11())
        changed = self.runtime_v11()
        changed["completion"] = "partial_verified"
        changed["observed_evidence"] = []
        with self.assertRaises(PersistenceError) as context:
            append_runtime_execution_evidence(store, changed)
        self.assertEqual(context.exception.code, "immutable_record_conflict")

    def test_v10_runtime_evidence_remains_readable_through_versioned_adapter(self):
        runtime = self.legacy_runtime()
        runtime["schema_version"] = "1.0"
        durable = from_runtime_execution_evidence(runtime)
        self.assertEqual(durable["schema_version"], "1.1")
        self.assertEqual(durable["verification_status"], "passed")
        self.assertNotIn("capability", durable)

    def test_preversioned_legacy_runtime_evidence_remains_readable(self):
        durable = from_runtime_execution_evidence(self.legacy_runtime())
        self.assertEqual(durable["schema_version"], "1.1")
        self.assertEqual(durable["verification_status"], "passed")
        self.assertNotIn("capability", durable)

    def test_missing_schema_version_with_v11_fields_is_rejected(self):
        runtime = self.legacy_runtime()
        runtime["capability"] = "project.inspect"
        with self.assertRaises(PersistenceError) as context:
            from_runtime_execution_evidence(runtime)
        self.assertEqual(context.exception.code, "runtime_evidence_schema_invalid")

    def test_runtime_record_claiming_durable_before_append_is_rejected(self):
        runtime = self.runtime_v11()
        runtime["durability"] = "durable"
        with self.assertRaises(PersistenceError) as context:
            from_runtime_execution_evidence(runtime)
        self.assertEqual(context.exception.code, "runtime_evidence_durability_invalid")


if __name__ == "__main__":
    unittest.main()
