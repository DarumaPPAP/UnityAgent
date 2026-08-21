"""Phase 6 evidence gate tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/GraphObservatory"))
from expansion_gate import evaluate_expansion_gate  # noqa: E402


class GraphExpansionGateTests(unittest.TestCase):
    def test_missing_usage_evidence_defers_expansion_as_unavailable(self) -> None:
        result = evaluate_expansion_gate({})
        self.assertEqual(result["decision"], "DEFER")
        self.assertEqual(result["evidence_status"], "unavailable")
        self.assertFalse(result["expansion_enabled"])

    def test_measured_kpi_thresholds_can_adopt_expansion(self) -> None:
        result = evaluate_expansion_gate({
            "same_task": True, "same_source_revision": True, "same_acceptance_criteria": True,
            "context_file_read_reduction": 0.30, "total_token_reduction": 0.30,
            "verifier_quality_delta": 0, "missed_dependency_delta": 0,
            "user_policy_loss": 0, "unverified_success_claims": 0, "stale_index": 0,
        })
        self.assertEqual(result["decision"], "ADOPT")
        self.assertTrue(result["expansion_enabled"])
