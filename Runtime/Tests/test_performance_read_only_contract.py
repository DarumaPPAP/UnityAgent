"""Performance Resultの静的Evidence、測定出典、Receiptを検査する。"""
from __future__ import annotations

import copy
import unittest

from Runtime.ReferenceImplementation.performance_read_only import PerformancePilotContractError, verify_performance_read_only


class PerformanceReadOnlyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        specialist = {"profile_id": "performance_subagent", "capability": "performance.analyze", "items": [], "required_evidence": ["performance_analysis"]}
        self.manifest = {"materialized_context": {"context_id": "ctx-performance", "context_fingerprint": {"value": "sha256:fixture"}, "specialist_context": specialist}}
        self.transported = {"context_id": "ctx-performance", "context_fingerprint": "sha256:fixture", "specialist_context": copy.deepcopy(specialist)}
        metadata = {"measurement_source": "none", "unity_version": "6000.3.15f1", "platform": "Windows", "graphics_api": "unknown", "capture_mode": "none", "build_type": "unknown", "scene_or_scope": "Scene/Main", "measurement_window": "unknown", "known_limitations": ["No runtime capture"], "validity": "not_measured"}
        self.result = {"status": "completed", "profile_id": "performance_subagent", "capability": "performance.analyze", "confirmed_facts": ["User reports high Main Thread frame time"], "measurement_summary": {"metadata": metadata, "metrics": [], "baseline": None, "candidate": None, "delta": None}, "bottleneck_classification": "unknown", "hypotheses": ["CPU work may contribute"], "rejected_hypotheses": [], "required_observations": ["Capture Profiler markers and frame timing on target"], "recommendations": ["Measure before changing source"], "observed_evidence": [{"type": "performance_analysis", "source_ref": "fixture:performance-symptom", "observation": "Symptom only; no runtime measurement"}], "evidence_level": "static", "known_limitations": ["CPU/GPU bottleneck not classified"], "received_context_id": "ctx-performance", "received_context_fingerprint": "sha256:fixture", "runtime_evaluation": "NOT_EVALUATED_RUNTIME"}

    def test_missing_measurement_stays_unknown(self) -> None:
        self.assertEqual(verify_performance_read_only(self.manifest, self.transported, self.result)["receipt_integrity"], "verified")
        for change in ({"bottleneck_classification": "cpu"}, {"required_observations": []}, {"runtime_evaluation": "VERIFIED_RUNTIME"}, {"evidence_level": "player"}, {"observed_evidence": []}, {"proposed_diff": "mutate"}):
            with self.subTest(change=change), self.assertRaises(PerformancePilotContractError):
                verify_performance_read_only(self.manifest, self.transported, {**self.result, **change})

    def test_fixture_metrics_are_explicitly_not_runtime_evidence(self) -> None:
        result = copy.deepcopy(self.result)
        result["measurement_summary"]["metadata"].update({"measurement_source": "fixture_input", "validity": "fixture_input"})
        result["measurement_summary"]["metrics"] = [{"name": "cpu_frame_time", "value": 33, "unit": "ms", "source": "fixture_input"}]
        result["bottleneck_classification"] = "cpu"
        self.assertEqual(verify_performance_read_only(self.manifest, self.transported, result)["runtime_evaluation"], "NOT_EVALUATED_RUNTIME")
        result["measurement_summary"]["metadata"]["validity"] = "target_device_verified"
        with self.assertRaises(PerformancePilotContractError):
            verify_performance_read_only(self.manifest, self.transported, result)

    def test_received_and_transported_receipt_mismatch_blocked(self) -> None:
        with self.assertRaisesRegex(PerformancePilotContractError, "received"):
            verify_performance_read_only(self.manifest, self.transported, {**self.result, "received_context_fingerprint": "sha256:wrong"})
        transported = {**self.transported, "context_id": "other"}
        with self.assertRaisesRegex(PerformancePilotContractError, "transported"):
            verify_performance_read_only(self.manifest, transported, self.result)

    def test_comparison_without_baseline_requests_observation(self) -> None:
        self.manifest["materialized_context"]["specialist_context"]["items"].append({"type": "task_fact", "key": "analysis_mode", "value": "comparison_requested"})
        self.transported["specialist_context"] = copy.deepcopy(self.manifest["materialized_context"]["specialist_context"])
        with self.assertRaisesRegex(PerformancePilotContractError, "baseline"):
            verify_performance_read_only(self.manifest, self.transported, self.result)
        result = {**self.result, "required_observations": ["Capture a comparable baseline on the same target"]}
        self.assertEqual(verify_performance_read_only(self.manifest, self.transported, result)["receipt_integrity"], "verified")


if __name__ == "__main__":
    unittest.main()
