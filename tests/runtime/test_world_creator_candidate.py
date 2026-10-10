"""WorldCreatorのProviderless Candidateと組合せ契約を検証する。"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import yaml

from unityagent.orchestration.routing.route_selector import load_routes, resolve_specialist, select_specialist_capability
from unityagent.orchestration.tool_routing.capability_request_builder import build_specialist_capability_requests, build_capability_requests
from unityagent.runtime.reference_implementation.candidate_profiles import CandidateProfileError, load_candidate_profile, validate_candidate_profile, resolve_candidate


ROOT = Path(__file__).resolve().parents[2]


class WorldCreatorCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_candidate_profile("world_creator_subagent")
        self.environment = {"project": {"exists": True, "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}}
        self.items = [{"category": "task_fact", "key": key, "value": value, "freshness": {"status": "current"}} for key, value in (("world_goal", "Build a dungeon"), ("requested_scope", "Assets/Scenes/Dungeon"))]

    def test_providerless_selection_and_empty_any_of(self) -> None:
        self.assertEqual((self.profile["execution_mode"], self.profile["provider_resolution"]), ("planning_only", "not_required"))
        self.assertEqual(self.profile["capabilities"], ["world.plan"])
        self.assertEqual(self.profile["required_evidence"], ["world_plan"])
        self.assertEqual(self.profile["capability_context"]["world.plan"]["any_of"], [])
        production = build_capability_requests(route_id="world-creation", project_root="/fixture", active_conditions={"project_fact_needed"})
        candidate = build_specialist_capability_requests("world-creation", "/fixture")
        self.assertEqual([item["capability"] for item in production], ["project.inspect"])
        self.assertEqual([item["capability"] for item in candidate], ["world.plan"])
        self.assertEqual(select_specialist_capability("world-creation", production + candidate), "world.plan")
        selected = resolve_specialist("world-creation", "world.plan", self.environment, pilot_enabled=True, context_items=self.items)
        self.assertEqual((selected["status"], selected["execution_mode"], selected["provider_resolution"], selected["receipt_required"]), ("selected", "planning_only", "not_required", False))
        self.assertEqual(load_routes(ROOT / "src/unityagent/orchestration/routing/task-routes.yaml")["routes"]["world-creation"]["specialist_phase"], "planning")

    def test_cross_field_combinations_and_phase_fail_closed(self) -> None:
        for changes in ({"execution_mode": "planning_only", "provider_resolution": "runtime_tool_broker"}, {"execution_mode": "read_only_analysis", "provider_resolution": "not_required"}):
            with self.subTest(changes=changes), self.assertRaises(CandidateProfileError):
                validate_candidate_profile({**self.profile, **changes})
        for mode, receipt in (("planning_only", True), ("read_only_analysis", False)):
            profile = copy.deepcopy(self.profile)
            profile["execution_mode"] = mode
            profile["provider_resolution"] = "not_required" if mode == "planning_only" else "runtime_tool_broker"
            profile["capability_context"]["world.plan"]["receipt_required"] = receipt
            with self.subTest(mode=mode), self.assertRaises(CandidateProfileError):
                validate_candidate_profile(profile)
        routes = ROOT / "src/unityagent/orchestration/routing/task-routes.yaml"
        self.assertEqual(load_routes(routes)["routes"]["world-creation"]["specialist_phase"], "planning")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile_path = root / "src/unityagent/runtime/reference_implementation/world-profile.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(yaml.safe_dump(self.profile), encoding="utf-8")
            (profile_path.parent / "candidate-specialists.yaml").write_text(yaml.safe_dump({"schema_version": "1.0", "kind": "candidate_specialist_catalog", "profiles": {"world_creator_subagent": "src/unityagent/runtime/reference_implementation/world-profile.yaml"}}), encoding="utf-8")
            route_path = root / "src/unityagent/orchestration/routing/task-routes.yaml"
            route_path.parent.mkdir(parents=True)
            route_path.write_text(yaml.safe_dump({"authority": "Orchestration", "routes": {"world-creation": {"specialist_profile": "world_creator_subagent", "specialist_pilot": True, "specialist_phase": "analysis"}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid phase"):
                load_routes(route_path)

    def test_missing_facts_disabled_pilot_and_unsupported_version(self) -> None:
        missing = resolve_specialist("world-creation", "world.plan", self.environment, pilot_enabled=True, context_items=self.items[:1])
        self.assertEqual((missing["status"], missing["reason_code"]), ("unavailable", "required_context_missing"))
        self.assertEqual(resolve_candidate(self.profile, "world.plan", self.environment, pilot_enabled=False)["reason_code"], "pilot_disabled")
        old = copy.deepcopy(self.environment)
        old["project"]["unity_version"] = "2022.3.62f1"
        self.assertEqual(resolve_specialist("world-creation", "world.plan", old, pilot_enabled=True)["reason_code"], "unity_version_unsupported")

    def test_pinned_hub_contract_matches_consumer(self) -> None:
        hub = yaml.safe_load((ROOT / "tests/runtime/fixtures/hub-world-creator-candidate-contract.yaml").read_text(encoding="utf-8"))
        self.assertEqual(hub["identity"], self.profile["profile_id"])
        self.assertEqual(set(hub["capabilities"]), set(self.profile["capabilities"]))
        self.assertEqual(hub["capabilities"]["world.plan"]["mode"], "planning_only")
        self.assertEqual(hub["boundaries"]["provider_resolution"], self.profile["provider_resolution"])
        self.assertEqual(hub["evidence"]["required_type"], self.profile["required_evidence"][0])
        self.assertEqual(hub["evidence"]["receipt"], "not_required_source_context_binding")
        self.assertFalse(self.profile["capability_context"]["world.plan"]["receipt_required"])
        self.assertEqual(hub["status"], "pilot_unregistered")
        self.assertEqual(hub["compatibility"]["unity_version"], "Unity 6.x+")
        self.assertEqual(self.profile["compatibility"]["unity_version_prefixes"], ["6000."])
        self.assertEqual(hub["boundaries"]["mutation"], "prohibited_during_pilot")
        self.assertEqual(hub["boundaries"]["route_reuse"], ["world-creation"])
        self.assertEqual(hub["evidence"]["unobserved_runtime"], self.profile["runtime_evaluation"])
        self.assertNotIn("backends", hub)


if __name__ == "__main__":
    unittest.main()
