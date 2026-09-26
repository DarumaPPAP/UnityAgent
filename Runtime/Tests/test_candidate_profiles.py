from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import yaml

from Orchestration.Routing.route_selector import resolve_specialist
from Orchestration.Routing.route_selector import select_specialist_capability
from Orchestration.ToolRouting.capability_request_builder import build_candidate_capability_requests
from Runtime.ReferenceImplementation.candidate_profiles import CandidateProfileError, load_candidate_profile, resolve_candidate, validate_candidate_profile


ROOT = Path(__file__).resolve().parents[2]


class CandidateProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_candidate_profile("graphics_subagent")
        self.environment = {"project": {"exists": True, "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}}
        self.items = [{"category": category, "key": key, "value": value, "freshness": {"status": "current"}} for category, key, value in (("project_fact", "unity_version", "6000.3.15f1"), ("project_fact", "render_pipeline", "urp"), ("project_fact", "relevant_source", "Assets/Example.shader"), ("task_fact", "rendering_symptom", "Pass missing"))]

    def test_generic_shape_and_activation_are_separate_from_context(self) -> None:
        self.assertEqual(validate_candidate_profile(self.profile), self.profile)
        missing = resolve_candidate(self.profile, "graphics.diagnose", self.environment, pilot_enabled=True)
        self.assertEqual((missing["status"], missing["reason_code"]), ("unavailable", "required_context_missing"))
        selected = resolve_candidate(self.profile, "graphics.diagnose", self.environment, pilot_enabled=True, context_items=self.items)
        self.assertEqual(selected["status"], "selected")
        self.assertEqual(resolve_candidate(self.profile, "graphics.diagnose", self.environment, pilot_enabled=False)["reason_code"], "pilot_disabled")
        missing_project = {"project": {"exists": False, "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}}
        self.assertEqual(resolve_candidate(self.profile, "graphics.diagnose", missing_project, pilot_enabled=True, context_items=self.items)["reason_code"], "activation_fact_unavailable")
        self.assertEqual(resolve_candidate(self.profile, "graphics.apply", self.environment, pilot_enabled=True)["status"], "unsupported")
        self.assertEqual(resolve_candidate(self.profile, "graphics.diagnose", self.environment, pilot_enabled=True, specialist_capability_mutates=True)["status"], "unsupported")
        self.assertEqual(resolve_candidate(self.profile, "graphics.diagnose", self.environment, pilot_enabled=True, context_items=self.items)["profile_id"], "graphics_subagent")
        stale = copy.deepcopy(self.items)
        stale[1]["freshness"]["status"] = "unknown"
        self.assertEqual(resolve_candidate(self.profile, "graphics.diagnose", self.environment, pilot_enabled=True, context_items=stale)["reason_code"], "required_context_missing")
        unsupported_pipeline = copy.deepcopy(self.items)
        unsupported_pipeline[1]["value"] = "custom"
        self.assertEqual(resolve_candidate(self.profile, "graphics.diagnose", self.environment, pilot_enabled=True, context_items=unsupported_pipeline)["reason_code"], "context_value_unsupported")

    def test_invalid_profile_and_catalog_path_fail_closed(self) -> None:
        duplicate = copy.deepcopy(self.profile)
        duplicate["capabilities"].append("graphics.diagnose")
        with self.assertRaises(CandidateProfileError):
            validate_candidate_profile(duplicate)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog = root / "Runtime/ReferenceImplementation/candidate-specialists.yaml"
            catalog.parent.mkdir(parents=True)
            catalog.write_text("schema_version: '1.0'\nkind: candidate_specialist_catalog\nprofiles:\n  graphics_subagent: ../outside.yaml\n", encoding="utf-8")
            with self.assertRaises(CandidateProfileError):
                load_candidate_profile("graphics_subagent", root=root)

    def test_second_candidate_is_data_only_for_generic_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = copy.deepcopy(self.profile)
            profile["profile_id"] = profile["audience"] = "sample_subagent"
            profile["goal_type"] = "sample.analyze"
            profile["capabilities"] = ["sample.analyze"]
            profile["capability_context"] = {"sample.analyze": profile["capability_context"]["graphics.diagnose"]}
            profile_path = root / "Runtime/ReferenceImplementation/sample-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(yaml.safe_dump(profile), encoding="utf-8")
            (profile_path.parent / "candidate-specialists.yaml").write_text(yaml.safe_dump({"schema_version": "1.0", "kind": "candidate_specialist_catalog", "profiles": {"sample_subagent": "Runtime/ReferenceImplementation/sample-profile.yaml"}}), encoding="utf-8")
            routes = root / "Orchestration/Routing/task-routes.yaml"
            routes.parent.mkdir(parents=True)
            routes.write_text(yaml.safe_dump({"authority": "Orchestration", "routes": {"sample-route": {"specialist_profile": "sample_subagent", "specialist_pilot": True, "specialist_phase": "analysis"}}}), encoding="utf-8")
            capability_route = root / "Orchestration/ToolRouting/capability-routing.yaml"
            capability_route.parent.mkdir(parents=True)
            capability_route.write_text(yaml.safe_dump({"routes": {"sample-route": {"candidate_capabilities": [{"capability": "sample.analyze", "operation_kind": "read", "required_evidence": ["graphics_diagnosis"], "preferred_surface": "project", "when": "always"}]}}}), encoding="utf-8")
            decision = resolve_specialist("sample-route", "sample.analyze", self.environment, root=root, pilot_enabled=True, context_items=self.items)
            self.assertEqual(decision["profile_id"], "sample_subagent")
            requests = build_candidate_capability_requests("sample-route", "/fixture", root=root)
            self.assertEqual(select_specialist_capability("sample-route", requests, root=root), "sample.analyze")

    def test_specialist_capability_is_selected_from_route_requests(self) -> None:
        requests = [{"capability": "project.inspect"}] + build_candidate_capability_requests("rendering-incident", "/fixture")
        self.assertEqual(select_specialist_capability("rendering-incident", requests), "graphics.diagnose")
        with self.assertRaisesRegex(ValueError, "no specialist capability match"):
            select_specialist_capability("rendering-incident", [{"capability": "project.inspect"}])
        with self.assertRaisesRegex(ValueError, "ambiguous specialist capability"):
            select_specialist_capability("rendering-incident", requests + [{"capability": "graphics.inspect"}])

    def test_pinned_hub_candidate_contract_matches_consumer_boundary(self) -> None:
        # UnitySubAgentHub PR #72, commit ef8dc9c32c1c46252cb146b330b6f49916010706.
        hub = yaml.safe_load((ROOT / "Runtime/Tests/Fixtures/hub-graphics-candidate-contract.yaml").read_text(encoding="utf-8"))
        self.assertEqual(hub["status"], "pilot_unregistered")
        self.assertEqual(hub["identity"], self.profile["profile_id"])
        self.assertEqual(set(hub["capabilities"]), set(self.profile["capabilities"]))
        self.assertTrue(all(value["mode"] == "read_only" for value in hub["capabilities"].values()))
        self.assertEqual(hub["evidence"]["required_type"], self.profile["required_evidence"][0])
        self.assertEqual(hub["evidence"]["unobserved_runtime"], self.profile["runtime_evaluation"])
        self.assertEqual(set(hub["compatibility"]["render_pipelines"]), set(self.profile["compatibility"]["context_values"]["project_fact:render_pipeline"]))
        self.assertEqual(self.profile["compatibility"]["unity_version_prefixes"], ["6000."])
        self.assertEqual(hub["boundaries"]["provider_resolution"], "unity_agent_tool_broker_only")
        self.assertEqual(self.profile["provider_resolution"], "runtime_tool_broker")
        self.assertEqual(hub["boundaries"]["mutation"], "prohibited_during_pilot")
        self.assertEqual(set(hub["boundaries"]["route_reuse"]), {"rendering-incident", "shader-change", "renderer-feature-change"})
        self.assertIn("observed_render_pipeline", hub["capabilities"]["graphics.inspect"]["requires"])
        self.assertIn("project_fact:render_pipeline", self.profile["capability_context"]["graphics.inspect"]["all_of"])
        self.assertIn("bounded_rendering_symptom", hub["capabilities"]["graphics.diagnose"]["requires"])
        self.assertIn("task_fact:rendering_symptom", self.profile["capability_context"]["graphics.diagnose"]["all_of"])


if __name__ == "__main__":
    unittest.main()
