"""Production分析契約のfixture。測定値は合成データであり実機Evidenceではない。"""
from __future__ import annotations

import copy
import unittest

from unityagent.runtime.contracts.reasoning_output import ReasoningOutputError, verify_reasoning_artifact


def context(profile, capability, observations):
    items = [{"type": "project_fact", "key": "observation:" + capability_id, "source": "evidence:" + identity, "revision": "sha256:" + "a" * 64, "value": {"capability": capability_id, "result": result, "observed_evidence": evidence, "target": {"surface": "project", "device_id": None}, "environment": {"unity_version": "6000.3.15f1"}}} for identity, capability_id, result, evidence in observations]
    return {"materialized_context": {"context_id": "ctx-analysis", "context_fingerprint": {"value": "sha256:" + "b" * 64}, "specialist_context": {"profile_id": profile, "capability": capability, "execution_mode": "read_only_analysis", "provider_resolution": "not_required", "items": items}}}


def common(profile, capability):
    return {"status": "completed", "profile_id": profile, "capability": capability, "execution_mode": "read_only_analysis", "provider_resolution": "not_required", "source_context_id": "ctx-analysis", "source_context_fingerprint": "sha256:" + "b" * 64, "confirmed_facts": [], "hypotheses": [], "rejected_hypotheses": [], "required_observations": ["Collect actual Unity runtime evidence"], "known_limitations": ["Synthetic fixture only"], "mutation_performed": False, "evidence_level": "runtime_reasoning", "runtime_evaluation": "RUNTIME_OBSERVED"}


def capture(identity, value):
    return {"capture_id": identity, "metadata": {"measurement_source": "fixture-recorder", "unity_version": "6000.3.15f1", "platform": "Windows", "graphics_api": "D3D12", "capture_mode": "editor", "build_type": "Editor", "scene_or_scope": "Assets/Scenes/Test", "measurement_window": "120 frames after warmup", "known_limitations": ["Synthetic test data"], "validity": "valid"}, "metrics": [{"name": "GPU frame", "value": value, "unit": "ms", "category": "gpu"}]}


class AnalysisReasoningOutputTests(unittest.TestCase):
    def graphics(self):
        manifest = context("graphics_subagent", "graphics.diagnose", [("project", "project.inspect", {"unity_version": "6000.3.15f1"}, ["project_fact"]), ("source", "source.read", {"path": "Assets/Example.shader", "content": "Shader Example {}"}, ["source_read"])])
        result = {**common("graphics_subagent", "graphics.diagnose"), "confirmed_facts": [{"statement": "Source contains Shader", "source_ref": "evidence:source"}], "observation_refs": ["evidence:project", "evidence:source"], "proposed_diff": None, "required_approval": "none"}
        return manifest, copy.deepcopy(result)

    def performance(self):
        captures = [capture("before", 12.0), capture("after", 9.0)]
        manifest = context("performance_subagent", "performance.analyze", [("profiler", "profiler.observe", {"measurements": captures}, ["profiler_capture"])])
        result = {**common("performance_subagent", "performance.analyze"), "measurements": [{"source_ref": "evidence:profiler", **item} for item in captures], "bottleneck_classification": "gpu", "classification_basis": [{"source_ref": "evidence:profiler", "capture_id": "after", "metric_names": ["GPU frame"]}], "comparison": {"baseline": {"source_ref": "evidence:profiler", "capture_id": "before"}, "candidate": {"source_ref": "evidence:profiler", "capture_id": "after"}, "deltas": [{"name": "GPU frame", "value": -3.0, "unit": "ms", "category": "gpu"}]}, "recommendations": ["Investigate rendering cost using controlled captures"]}
        return manifest, copy.deepcopy(result)

    def test_graphics_and_performance_are_allowlisted_reasoning_contracts(self):
        for domain, fixture in (("graphics", self.graphics), ("performance", self.performance)):
            with self.subTest(domain=domain):
                manifest, result = fixture()
                verified = verify_reasoning_artifact(f"src/unityagent/runtime/contracts/{domain}-analysis-result.schema.json", manifest, result)
                self.assertEqual(verified["status"], "runtime_contract_verified")
                self.assertEqual(verified["evidence_level"], "runtime_reasoning")

    def test_stale_context_mutation_and_unobserved_sources_are_rejected(self):
        for domain, fixture in (("graphics", self.graphics), ("performance", self.performance)):
            for field, value in (("source_context_fingerprint", "stale"), ("mutation_performed", True), ("provider_id", "invented"), ("editor_verified", True), ("confirmed_facts", [{"statement": "invented", "source_ref": "evidence:absent"}])):
                with self.subTest(domain=domain, field=field):
                    manifest, result = fixture()
                    result[field] = value
                    with self.assertRaises(ReasoningOutputError):
                        verify_reasoning_artifact(f"src/unityagent/runtime/contracts/{domain}-analysis-result.schema.json", manifest, result)

    def test_graphics_diff_requires_approval_and_required_sources(self):
        manifest, result = self.graphics()
        result["proposed_diff"] = "Proposed source diff; not applied"
        with self.assertRaisesRegex(ReasoningOutputError, "approval"):
            verify_reasoning_artifact("src/unityagent/runtime/contracts/graphics-analysis-result.schema.json", manifest, result)
        result["required_approval"] = "required_before_apply"
        verify_reasoning_artifact("src/unityagent/runtime/contracts/graphics-analysis-result.schema.json", manifest, result)
        manifest["materialized_context"]["specialist_context"]["items"].pop()
        with self.assertRaises(ReasoningOutputError):
            verify_reasoning_artifact("src/unityagent/runtime/contracts/graphics-analysis-result.schema.json", manifest, result)

    def test_performance_cannot_invent_values_metadata_or_target_level(self):
        for field, value in (("platform", "PS5"), ("capture_mode", "target_device"), ("graphics_api", "Vulkan"), ("validity", "fixture_input")):
            manifest, result = self.performance()
            result["measurements"][0]["metadata"][field] = value
            with self.subTest(field=field), self.assertRaises(ReasoningOutputError):
                verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)
        manifest, result = self.performance()
        result["measurements"][0]["metrics"][0]["value"] = 1.0
        with self.assertRaises(ReasoningOutputError):
            verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)

    def test_no_measurement_keeps_unknown_and_requests_observation(self):
        manifest, result = self.performance()
        manifest["materialized_context"]["specialist_context"]["items"][0]["value"]["result"] = {"measurements": []}
        result.update(measurements=[], bottleneck_classification="unknown", classification_basis=[], comparison=None)
        verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)
        result["bottleneck_classification"] = "gpu"
        with self.assertRaises(ReasoningOutputError):
            verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)

    def test_limited_editor_snapshot_cannot_support_bottleneck_or_comparison(self):
        manifest, result = self.performance()
        for capture in manifest["materialized_context"]["specialist_context"]["items"][0]["value"]["result"]["measurements"]:
            capture["metadata"]["validity"] = "limited"
        for capture in result["measurements"]:
            capture["metadata"]["validity"] = "limited"
        with self.assertRaises(ReasoningOutputError):
            verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)
        result.update(bottleneck_classification="unknown", classification_basis=[], comparison=None)
        verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)

    def test_comparison_requires_same_conditions_and_exact_delta(self):
        manifest, result = self.performance()
        result["comparison"]["deltas"][0]["value"] = -4.0
        with self.assertRaises(ReasoningOutputError):
            verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)
        manifest, result = self.performance()
        # Both observations carry the different condition; this is not merely a copied-metadata check.
        manifest["materialized_context"]["specialist_context"]["items"][0]["value"]["result"]["measurements"][1]["metadata"]["build_type"] = "Development Player"
        result["measurements"][1]["metadata"]["build_type"] = "Development Player"
        with self.assertRaises(ReasoningOutputError):
            verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)

    def test_wrong_metric_category_and_nonfinite_measurement_are_rejected(self):
        manifest, result = self.performance()
        result["bottleneck_classification"] = "cpu"
        with self.assertRaises(ReasoningOutputError):
            verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)
        for value in (float("nan"), float("inf"), True):
            manifest, result = self.performance()
            result["measurements"][0]["metrics"][0]["value"] = value
            with self.subTest(value=value), self.assertRaises(ReasoningOutputError):
                verify_reasoning_artifact("src/unityagent/runtime/contracts/performance-analysis-result.schema.json", manifest, result)
