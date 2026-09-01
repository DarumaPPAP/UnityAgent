from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Verification.player_verification import classify_editor_player, verify_target_performance


class PlayerVerificationTests(unittest.TestCase):
    def player_result(self, *, command="observe.frame", evidence_class="target_performance_sample", payload=None):
        return {
            "status": "passed",
            "failure_class": None,
            "provider_ref": "player_runtime",
            "command_id": command,
            "target_device_id": "switch-devkit-1",
            "payload": payload or {
                "sample_count": 240,
                "duration_seconds": 4.0,
                "metrics": {"frame_ms_p95": 15.5},
            },
            "evidence": ["player_observation"],
            "evidence_class": evidence_class,
        }

    def requirement(self):
        return {
            "target_device_id": "switch-devkit-1",
            "minimum_samples": 120,
            "minimum_duration_seconds": 2.0,
            "metric": "frame_ms_p95",
            "comparator": "<=",
            "threshold": 16.67,
            "proof_contract_ref": "switch-frame-budget-v1",
        }

    def test_editor_pass_player_unavailable_is_partial_not_pass(self):
        result = classify_editor_player(
            editor_result={"status": "passed", "evidence": ["compile_observation"]},
            player_result={
                "status": "failed",
                "failure_class": "unavailable",
                "provider_ref": "player_runtime",
                "evidence": [],
            },
        )
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["editor"]["verified"])
        self.assertFalse(result["player"]["verified"])
        self.assertFalse(result["verified"])

    def test_editor_and_player_pass_are_still_separate_evidence_sets(self):
        result = classify_editor_player(
            editor_result={"status": "passed", "evidence": ["compile_observation"]},
            player_result=self.player_result(),
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["editor"]["evidence"], ["compile_observation"])
        self.assertEqual(result["player"]["evidence"], ["player_observation"])
        self.assertFalse(result["editor_pass_implies_player_pass"])

    def test_non_player_provider_cannot_satisfy_player_verification(self):
        player = self.player_result()
        player["provider_ref"] = "native_unity_editor"
        result = classify_editor_player(
            editor_result={"status": "passed", "evidence": ["compile_observation"]},
            player_result=player,
        )
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["player"]["verified"])

    def test_single_frame_sample_is_not_target_performance_proof(self):
        player = self.player_result(
            payload={
                "sample_count": 1,
                "duration_seconds": 0.016,
                "metrics": {"frame_ms_p95": 10.0},
            }
        )
        result = verify_target_performance(player, requirement=self.requirement())
        self.assertEqual(result["status"], "not_observed")
        self.assertEqual(result["evidence_strength"], "target_performance_sample")
        self.assertFalse(result["proof_observed"])

    def test_runtime_observation_is_not_promoted_to_performance_proof(self):
        player = self.player_result(evidence_class="runtime_observation")
        result = verify_target_performance(player, requirement=self.requirement())
        self.assertEqual(result["evidence_strength"], "runtime_observation")
        self.assertFalse(result["proof_observed"])

    def test_sufficient_target_samples_can_verify_explicit_performance_contract(self):
        result = verify_target_performance(self.player_result(), requirement=self.requirement())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["evidence_strength"], "target_performance_proof")
        self.assertTrue(result["proof_observed"])
        self.assertTrue(result["meets_target"])
        self.assertEqual(result["performance_outcome"], "target_met")

    def test_observed_target_performance_failure_remains_failure(self):
        player = self.player_result(
            payload={
                "sample_count": 240,
                "duration_seconds": 4.0,
                "metrics": {"frame_ms_p95": 24.0},
            }
        )
        result = verify_target_performance(player, requirement=self.requirement())
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["proof_observed"])
        self.assertFalse(result["meets_target"])
        self.assertIsNone(result["failure_class"])
        self.assertEqual(result["performance_outcome"], "target_missed")

    def test_target_device_mismatch_cannot_prove_target_performance(self):
        requirement = self.requirement()
        requirement["target_device_id"] = "different-device"
        result = verify_target_performance(self.player_result(), requirement=requirement)
        self.assertEqual(result["status"], "not_observed")
        self.assertFalse(result["proof_observed"])
        self.assertEqual(result["failure_class"], "precondition_failed")


if __name__ == "__main__":
    unittest.main()
