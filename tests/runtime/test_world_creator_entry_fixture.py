"""World Planning EntryからProviderless Plan ArtifactまでのRepository fixture。"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import ValidationError

from unityagent.context.manifest.build_context_manifest import build as build_context_manifest
from unityagent.context.selection.project_context_inputs import derive_context_inputs
from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane, validate_entry_request
from unityagent.orchestration.routing.route_selector import load_routes, resolve_specialist, select_route, select_specialist_capability, task_fingerprint_from_intent
from unityagent.orchestration.tool_routing.capability_request_builder import build_specialist_capability_requests, build_capability_requests, conditions_for_intent
from unityagent.runtime.reference_implementation.world_planning import WorldPlanContractError, verify_world_plan
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.tool_broker import ToolBroker


ROOT = Path(__file__).resolve().parents[2]


class WorldCreatorEntryFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "Project"
        for folder in ("Assets", "Packages", "ProjectSettings"):
            (self.project / folder).mkdir(parents=True)
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.15f1\n", encoding="utf-8")
        self.snapshot = {"project": {"root": str(self.project), "exists": True, "identity_status": "bound", "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}, "build": {"requested_target": "unknown"}}

    def entry(self, world_goal: str = "Build a dungeon", scene_scope: str = "Assets/Scenes/Dungeon", **options) -> dict:
        return {"schema_version": "2.0", "request_id": "world-fixture", "entry_point": "codex_plugin", "project_root": str(self.project), "intent": {"kind": "world_planning", "world_goal": world_goal, "scene_scope": scene_scope, **options}}

    def prepare(self, entry: dict):
        validate_entry_request(entry)
        fingerprint = task_fingerprint_from_intent(entry["intent"], self.snapshot, project_root=entry["project_root"], policy_allowed=True)
        route = select_route(fingerprint, load_routes(ROOT / "src/unityagent/orchestration/routing/task-routes.yaml"))
        conditions = conditions_for_intent(entry["intent"], fingerprint)
        production = build_capability_requests(route_id=route["route_id"], project_root=entry["project_root"], active_conditions=conditions)
        candidate = build_specialist_capability_requests(route["route_id"], entry["project_root"], active_conditions=conditions)
        capability = select_specialist_capability(route["route_id"], production + candidate)
        inputs = derive_context_inputs(entry["project_root"], self.snapshot, entry["intent"])
        selection = resolve_specialist(route["route_id"], capability, self.snapshot, pilot_enabled=True, context_items=inputs["specialist_items"])
        manifest = build_context_manifest("world-fixture", route["route_id"], project_facts=inputs["project_facts"], bindings=inputs["bindings"], capability_ids=[item["capability"] for item in production], active_conditions=conditions, specialist_selection=selection, specialist_items=inputs["specialist_items"], specialist_tags=inputs["specialist_tags"], required_specialist_keys=inputs["required_specialist_keys"])
        return fingerprint, route, production, candidate, selection, inputs, manifest

    def package(self, identifier: str, goal: str, domain_hint: str, depends_on: list[str] | None = None) -> dict:
        return {"id": identifier, "goal": goal, "scope": "Scene area", "domain_hint": domain_hint, "depends_on": depends_on or [], "constraints": ["Preserve existing scene content"], "acceptance_criteria": ["Reviewable result defined"], "required_evidence": ["static_review"]}

    def result(self, manifest: dict, entry: dict, packages: list[dict], *, zones: list[str] | None = None) -> dict:
        intent = entry["intent"]
        view = manifest["materialized_context"]
        edges = [{"before": parent, "after": package["id"]} for package in packages for parent in package["depends_on"]]
        open_decisions = []
        if "environment_type" not in intent:
            open_decisions.append("environment_type is undecided")
        if "desired_mood" not in intent:
            open_decisions.append("desired_mood is undecided")
        if "target_platforms" not in intent and self.snapshot["build"]["requested_target"] == "unknown":
            open_decisions.append("target_platform is undecided")
        plan = {"world_goal": intent["world_goal"], "scene_scope": intent["scene_scope"], "environment_type": intent.get("environment_type"), "visual_intent": intent.get("desired_mood"), "zones": zones or [], "camera_requirements": ["Review player camera distance"], "lighting_requirements": ["Define lighting direction"], "content_requirements": ["Identify required assets"], "technical_constraints": ["Preserve existing project architecture"], "performance_constraints": ["Set budget after target platform decision"], "platform_constraints": list(intent.get("target_platforms", [])), "prohibited_changes": list(intent.get("prohibited_changes", [])), "acceptance_criteria": list(intent.get("acceptance_criteria", ["Human reviews the plan"])), "work_packages": packages, "dependencies": edges, "required_evidence": ["world_plan", "static_review"], "open_decisions": open_decisions, "human_review_required": True, "direct_unity_mutation": False, "automatic_visual_acceptance": False}
        return {"status": "completed", "profile_id": "world_creator_subagent", "capability": "world.plan", "execution_mode": "planning_only", "provider_resolution": "not_required", "source_context_id": view["context_id"], "source_context_fingerprint": view["context_fingerprint"]["value"], "world_plan": plan, "evidence_level": "static", "known_limitations": ["No Scene, Editor, Player, or target device execution"], "runtime_evaluation": "NOT_EVALUATED_RUNTIME"}

    def test_dungeon_entry_to_providerless_world_plan(self) -> None:
        entry = self.entry(environment_type="dungeon", desired_mood="dark exploration")
        with patch.object(ToolBroker, "resolve", side_effect=AssertionError("provider resolution forbidden")) as resolve, patch.object(ToolBroker, "dispatch", side_effect=AssertionError("provider dispatch forbidden")) as dispatch:
            fingerprint, route, production, candidate, selection, inputs, manifest = self.prepare(entry)
            packages = [self.package("layout", "Define traversable zones", "generic_unity"), self.package("lighting", "Define lighting intent", "visual", ["layout"]), self.package("graphics", "Define rendering validation needs", "graphics", ["lighting"]), self.package("performance", "Define performance evidence needs", "performance", ["graphics"])]
            result = self.result(manifest, entry, packages, zones=["entrance", "chambers", "exit"])
            report = verify_world_plan(manifest, result)
            resolve.assert_not_called()
            dispatch.assert_not_called()
        self.assertEqual((fingerprint["artifact"], route["route_id"], [item["capability"] for item in candidate]), ("world", "world-creation", ["world.plan"]))
        self.assertEqual([item["capability"] for item in production], ["project.inspect"])
        self.assertEqual((selection["execution_mode"], selection["provider_resolution"], selection["receipt_required"]), ("planning_only", "not_required", False))
        self.assertEqual(inputs["specialist_tags"], {"world"})
        self.assertEqual(report["evidence_type"], "world_plan")
        self.assertNotIn("received_context_id", result)
        self.assertEqual(len(result["world_plan"]["dependencies"]), 3)

    def test_boss_arena_live_stage_multizone_and_existing_scene_fixtures(self) -> None:
        cases = [
            ("Boss Arena", "Assets/Scenes/Arena", {}, ["generic_unity", "visual", "graphics", "performance"], ["arena"], 3),
            ("Live Stage", "Assets/Scenes/Stage", {"desired_mood": "concert spectacle"}, ["visual", "content"], ["stage"], 1),
            ("Multi-zone World", "Assets/Scenes/World", {}, ["generic_unity", "visual", "performance"], ["hub", "forest", "ruins"], 2),
            ("Expand existing scene", "Assets/Scenes/Existing", {"prohibited_changes": ["Do not alter player spawn", "Do not delete authored props"]}, ["generic_unity", "content"], ["existing", "extension"], 1),
        ]
        for goal, scope, options, hints, zones, edge_count in cases:
            with self.subTest(goal=goal):
                entry = self.entry(goal, scope, **options)
                *_, manifest = self.prepare(entry)
                packages = [self.package(f"package-{index}", f"Define {hint} outcome", hint, [f"package-{index-1}"] if index else []) for index, hint in enumerate(hints)]
                result = self.result(manifest, entry, packages, zones=zones)
                self.assertEqual(verify_world_plan(manifest, result)["status"], "fixture_contract_verified")
                self.assertEqual(len(result["world_plan"]["dependencies"]), edge_count)
                self.assertEqual({item["domain_hint"] for item in packages}, set(hints))
                self.assertTrue(result["world_plan"]["human_review_required"])
                self.assertEqual(result["world_plan"]["prohibited_changes"], options.get("prohibited_changes", []))

    def test_missing_entry_fields_and_unavailable_reasoning_runtime_block(self) -> None:
        for key in ("world_goal", "scene_scope"):
            entry = self.entry()
            del entry["intent"][key]
            with self.subTest(key=key), self.assertRaises(ValidationError):
                validate_entry_request(entry)
        revisions = {name: "fixture-v1" for name in ("architecture_version", "policy_revision", "prompt_revision", "context_revision", "graph_revision", "runtime_profile_revision", "tool_schema_revision", "checkpoint_schema_revision", "evidence_schema_revision", "eval_contract_revision")}
        def observation(request, *args, **kwargs):
            self.assertEqual(request["capability"], "project.inspect")
            return {"status": "completed"}
        with patch.object(ToolBroker, "resolve", side_effect=AssertionError("world.plan must not resolve Provider")) as resolve, patch.object(ToolBroker, "dispatch", side_effect=observation) as dispatch:
            response = UnityAgentControlPlane(self.project.parent / "state").execute(self.entry(), environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True), executors={}, definition_fingerprint={"schema_version": "1.0", **revisions})
            resolve.assert_not_called()
            dispatch.assert_called_once()
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["results"][-1]["runtime_failure"]["failure_class"], "runner_unavailable")

    def test_platform_arrays_are_preserved_and_conflicts_are_open(self) -> None:
        self.snapshot["build"]["requested_target"] = "Windows"
        entry = self.entry(target_platforms=["Quest", "Windows"], prohibited_changes=["Keep player spawn", "Keep authored props"], acceptance_criteria=["Readable navigation", "Human visual review"])
        *_, manifest = self.prepare(entry)
        result = self.result(manifest, entry, [self.package("layout", "Define layout", "generic_unity")])
        self.assertEqual(verify_world_plan(manifest, result)["evidence_type"], "world_plan")
        self.assertEqual(result["world_plan"]["platform_constraints"], ["Quest", "Windows"])
        self.assertEqual(result["world_plan"]["prohibited_changes"], entry["intent"]["prohibited_changes"])
        self.assertEqual(result["world_plan"]["acceptance_criteria"], entry["intent"]["acceptance_criteria"])
        missing = copy.deepcopy(result)
        missing["world_plan"]["platform_constraints"] = ["Quest"]
        with self.assertRaisesRegex(WorldPlanContractError, "dropped supplied"):
            verify_world_plan(manifest, missing)
        conflict_entry = self.entry(target_platforms=["Quest"])
        *_, conflict_manifest = self.prepare(conflict_entry)
        conflict = self.result(conflict_manifest, conflict_entry, [self.package("layout", "Define layout", "generic_unity")])
        conflict["world_plan"]["platform_constraints"].append("Windows")
        with self.assertRaisesRegex(WorldPlanContractError, "conflicting target"):
            verify_world_plan(conflict_manifest, conflict)
        conflict["world_plan"]["open_decisions"].append("target_platform_conflict: Quest requested, Windows observed")
        self.assertEqual(verify_world_plan(conflict_manifest, conflict)["evidence_type"], "world_plan")

    def test_stale_context_fake_receipt_mutation_and_hidden_decisions_fail(self) -> None:
        entry = self.entry()
        *_, manifest = self.prepare(entry)
        result = self.result(manifest, entry, [self.package("layout", "Define layout", "generic_unity")])
        for change in ({"source_context_fingerprint": "sha256:stale"}, {"received_context_id": "fake"}, {"provider_ref": "fake"}):
            with self.subTest(change=change), self.assertRaises(WorldPlanContractError):
                verify_world_plan(manifest, {**result, **change})
        for key, value in (("human_review_required", False), ("direct_unity_mutation", True), ("automatic_visual_acceptance", True), ("environment_type", "dungeon"), ("open_decisions", [])):
            modified = copy.deepcopy(result)
            modified["world_plan"][key] = value
            with self.subTest(key=key), self.assertRaises(WorldPlanContractError):
                verify_world_plan(manifest, modified)
        modified = copy.deepcopy(result)
        modified["world_plan"]["work_packages"][0]["goal"] = "save scene"
        with self.assertRaises(WorldPlanContractError):
            verify_world_plan(manifest, modified)
        for field, value in (("domain_hint", "graphics_subagent"), ("route_id", "rendering-incident"), ("provider_id", "world_creator_provider")):
            modified = copy.deepcopy(result)
            modified["world_plan"]["work_packages"][0][field] = value
            with self.subTest(field=field), self.assertRaises(WorldPlanContractError):
                verify_world_plan(manifest, modified)
        cyclic = copy.deepcopy(result)
        cyclic["world_plan"]["work_packages"].append(self.package("lighting", "Define lighting", "visual", ["layout"]))
        cyclic["world_plan"]["work_packages"][0]["depends_on"] = ["lighting"]
        cyclic["world_plan"]["dependencies"] = [{"before": "layout", "after": "lighting"}, {"before": "lighting", "after": "layout"}]
        with self.assertRaisesRegex(WorldPlanContractError, "cycle"):
            verify_world_plan(manifest, cyclic)


if __name__ == "__main__":
    unittest.main()
