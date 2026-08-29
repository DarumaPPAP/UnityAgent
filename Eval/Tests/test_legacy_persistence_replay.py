import unittest

from Eval.Replay.legacy_persistence_graph import (
    LegacyReplayError as GraphReplayError,
    normalize_legacy_run_state,
    reject_continuation_decision_as_durable_state,
)
from Eval.Replay.legacy_persistence_memory import normalize_legacy_layered_records


class LegacyPersistenceReplayTests(unittest.TestCase):
    def test_graph_replay_requires_exact_topology_mapping(self):
        legacy = {
            "run_id": "legacy-run",
            "status": "running",
            "updated_at": "2026-08-29T00:00:00Z",
            "nodes": [
                {
                    "id": "inspect_sources",
                    "status": "running",
                    "attempts": 2,
                    "last_action": "read",
                    "last_evidence": ["ev-1"],
                }
            ],
        }
        normalized = normalize_legacy_run_state(
            legacy,
            parent_graph_id="development",
            subgraph_by_node={"inspect_sources": "investigation"},
        )
        self.assertEqual(normalized["workflow_state"]["active_subgraph_id"], "investigation")
        self.assertEqual(normalized["loop_control_states"], [])
        self.assertIsNone(normalized["execution_state"]["current_action_id"])
        with self.assertRaises(GraphReplayError):
            normalize_legacy_run_state(legacy, parent_graph_id="development", subgraph_by_node={})
        with self.assertRaises(GraphReplayError):
            reject_continuation_decision_as_durable_state({"controller": "native_continuation"})

    def test_layered_memory_replay_separates_raw_evidence_and_memory(self):
        records = [
            {
                "memory_id": "ev-legacy",
                "layer": "L0_raw_evidence",
                "statement": "raw",
                "raw_refs": ["Evidence/raw/ev-legacy.txt"],
                "confidence": "verified",
                "scope_class": "portable_artifact",
                "sha256": "b" * 64,
            },
            {
                "memory_id": "atom-1",
                "layer": "L1_atom",
                "statement": "observation",
                "raw_refs": ["Evidence/raw/ev-legacy.txt"],
                "confidence": "verified",
                "scope_class": "portable_artifact",
                "created_at": "2026-08-29T00:00:00Z",
                "applicability": ["Unity"],
                "limits": [],
            },
            {
                "memory_id": "scenario-1",
                "layer": "L2_scenario",
                "statement": "scenario",
                "atom_refs": ["atom-1"],
                "confidence": "probable",
                "scope_class": "portable_artifact",
                "created_at": "2026-08-29T00:00:00Z",
                "applicability": ["Unity"],
                "limits": ["one case"],
            },
        ]
        result = normalize_legacy_layered_records(records)
        self.assertEqual([item["evidence_id"] for item in result["evidence_candidates"]], ["ev-legacy"])
        memory = {item["memory_id"]: item for item in result["memory_records"]}
        self.assertEqual(memory["atom-1"]["source_evidence_refs"], ["ev-legacy"])
        self.assertEqual(memory["scenario-1"]["source_memory_refs"], ["atom-1"])
        self.assertEqual(memory["scenario-1"]["source_evidence_refs"], ["ev-legacy"])


if __name__ == "__main__":
    unittest.main()
