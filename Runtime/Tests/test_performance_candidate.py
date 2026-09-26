"""Performance Candidateが既存Generic経路だけで選出されることを確認する。"""
from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

from Orchestration.Routing.route_selector import resolve_specialist, select_specialist_capability
from Orchestration.ToolRouting.capability_request_builder import build_candidate_capability_requests, build_capability_requests
from Runtime.ReferenceImplementation.candidate_profiles import load_candidate_profile


ROOT = Path(__file__).resolve().parents[2]


class PerformanceCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = {"project": {"exists": True, "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}}
        self.items = [{"category": category, "key": key, "value": value, "freshness": {"status": "current"}} for category, key, value in (("project_fact", "unity_version", "6000.3.15f1"), ("platform_fact", "requested_target", "Windows"), ("task_fact", "performance_symptom", "Main Thread frame time is high"), ("task_fact", "requested_scope", "Scene/Main"))]

    def test_profile_and_route_select_one_read_only_candidate_capability(self) -> None:
        profile = load_candidate_profile("performance_subagent")
        self.assertEqual((profile["profile_id"], profile["display_name"]), ("performance_subagent", "PerformanceSubAgent"))
        self.assertEqual(profile["capabilities"], ["performance.analyze"])
        self.assertEqual(profile["required_evidence"], ["performance_analysis"])
        production = build_capability_requests(route_id="performance-experiment", project_root="/fixture", active_conditions={"project_fact_needed"})
        candidate = build_candidate_capability_requests("performance-experiment", "/fixture", active_conditions={"project_fact_needed"})
        self.assertEqual([request["capability"] for request in production], ["project.inspect"])
        self.assertEqual([request["capability"] for request in candidate], ["performance.analyze"])
        self.assertEqual(select_specialist_capability("performance-experiment", production + candidate), "performance.analyze")
        selected = resolve_specialist("performance-experiment", "performance.analyze", self.snapshot, pilot_enabled=True, context_items=self.items)
        self.assertEqual((selected["status"], selected["profile_id"], selected["receipt_required"]), ("selected", "performance_subagent", True))
        registry = yaml.safe_load((ROOT / "Runtime/Tooling/provider_registry.yaml").read_text(encoding="utf-8"))
        self.assertFalse(any("performance.analyze" in provider.get("capabilities", {}) for provider in registry["providers"].values()))
        self.assertFalse(any("performance_subagent" in str(provider) for provider in registry["providers"].values()))

    def test_missing_context_unsupported_version_and_disabled_pilot_are_distinct(self) -> None:
        missing = resolve_specialist("performance-experiment", "performance.analyze", self.snapshot, pilot_enabled=True, context_items=self.items[:1])
        self.assertEqual((missing["status"], missing["reason_code"]), ("unavailable", "required_context_missing"))
        self.assertIn("platform_fact:requested_target", missing["required_observations"])
        self.assertEqual(resolve_specialist("performance-experiment", "performance.analyze", self.snapshot, pilot_enabled=False)["reason_code"], "pilot_disabled")
        old = copy.deepcopy(self.snapshot)
        old["project"]["unity_version"] = "2022.3.62f1"
        self.assertEqual(resolve_specialist("performance-experiment", "performance.analyze", old, pilot_enabled=True)["reason_code"], "unity_version_unsupported")

    def test_pinned_hub_contract_matches_consumer_boundary(self) -> None:
        hub = yaml.safe_load((ROOT / "Runtime/Tests/Fixtures/hub-performance-candidate-contract.yaml").read_text(encoding="utf-8"))
        profile = load_candidate_profile("performance_subagent")
        self.assertEqual(hub["status"], "pilot_unregistered")
        self.assertEqual(hub["identity"], profile["profile_id"])
        self.assertEqual(set(hub["capabilities"]), set(profile["capabilities"]))
        self.assertTrue(all(item["mode"] == "read_only" for item in hub["capabilities"].values()))
        self.assertEqual(hub["evidence"]["required_type"], profile["required_evidence"][0])
        self.assertEqual(hub["evidence"]["unobserved_runtime"], profile["runtime_evaluation"])
        self.assertEqual(hub["compatibility"]["unity_version"], "Unity 6.x+")
        self.assertEqual(profile["compatibility"]["unity_version_prefixes"], ["6000."])
        self.assertEqual(hub["boundaries"]["provider_resolution"], "unity_agent_tool_broker_only")
        self.assertEqual(profile["provider_resolution"], "runtime_tool_broker")
        self.assertEqual(hub["boundaries"]["mutation"], "prohibited_during_pilot")
        self.assertEqual(hub["evidence"]["receipt"], "generated_transported_received_identity_and_fingerprint_match")
        self.assertTrue(profile["capability_context"]["performance.analyze"]["receipt_required"])
        self.assertEqual(hub["boundaries"]["route_reuse"], ["performance-experiment"])


if __name__ == "__main__":
    unittest.main()
