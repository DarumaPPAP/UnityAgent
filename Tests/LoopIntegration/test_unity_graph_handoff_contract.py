"""UnityAgent / Unity-Graph-Engineering handoff boundary tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/LoopIntegration"))
from handoff import build_from_loop, build_to_loop, validate_handoff  # noqa: E402
from improvement_candidate import build_improvement_candidate, validate_improvement_candidate  # noqa: E402


class UnityGraphHandoffContractTests(unittest.TestCase):
    def _manifest(self, decision: str = "within_budget") -> dict:
        return {
            "schema_version": "3.1",
            "manifest": {"id": "manifest-1"},
            "task": {"id": "task-1", "route": "csharp-local-fix", "fingerprint": {}},
            "harness": {"task_contract": {"source_path": ".ai/harness/task-contracts/csharp-local-fix.yaml"}},
            "budget": {
                "contract": ".ai/context-budget.yaml",
                "profile": "tight",
                "decision": decision,
                "blocking_reasons": [] if decision == "within_budget" else ["context_budget_not_ready"],
            },
        }

    def _harness(self, *, mutating: bool = False) -> dict:
        return {
            "execution_profile": "generic_planning",
            "risk_level": "R1" if mutating else "R0",
            "allowed_mutations": ["source_edit"] if mutating else [],
            "prohibited_mutations": [],
            "quality_gates": {"required": [], "conditional": []},
            "unresolved_bindings": [],
        }

    def test_to_loop_handoff_contains_v2_fields_not_transcript_or_execution_budget(self) -> None:
        document = build_to_loop(
            {
                "task_id": "task-1",
                "route_id": "csharp-local-fix",
                "selected_contexts": [{"id": "csharp-local-fix", "source_hash": "abc"}],
            },
            self._manifest(),
            self._harness(),
        )
        self.assertEqual(validate_handoff(document, "to_loop"), [])
        self.assertEqual(document["schema_version"], "2.0")
        self.assertEqual(document["context_manifest_schema_version"], "3.1")
        self.assertEqual(document["context_budget_decision"]["decision"], "within_budget")
        self.assertNotIn("transcript", document)
        self.assertNotIn("budget", document)

    def test_mutation_handoff_requires_context_budget_within_budget(self) -> None:
        document = build_to_loop(
            {"task_id": "task-1", "route_id": "csharp-local-fix", "selected_contexts": []},
            self._manifest("compression_required"),
            self._harness(mutating=True),
        )
        self.assertIn(
            "mutation handoff requires context budget decision within_budget",
            validate_handoff(document, "to_loop"),
        )

    def test_loop_result_is_reference_only(self) -> None:
        document = build_from_loop({
            "run_id": "run-1",
            "node_id": "node-1",
            "attempt": 1,
            "verdict": "APPROVE",
            "evidence_refs": ["ev-1"],
            "gate_results": {},
            "failure_signature": None,
            "stop_reason": None,
            "metrics_ref": "m-1",
            "next_transition": "complete",
        })
        self.assertEqual(validate_handoff(document, "from_loop"), [])
        self.assertEqual(document["schema_version"], "2.0")

    def test_improvement_candidate_requires_evidence_and_human_review_for_acceptance(self) -> None:
        candidate = build_improvement_candidate({
            "run_id": "run-1",
            "evidence_refs": ["ev-1"],
            "canonical_owner": ".ai/context-packs",
            "target": "context",
            "failure_signature": "miss",
            "boundary_pair": "context-selection",
        })
        self.assertEqual(validate_improvement_candidate(candidate), [])
        candidate["status"] = "accepted"
        self.assertIn("accepted candidate requires human_review_ref", validate_improvement_candidate(candidate))
