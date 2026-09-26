"""Performance Intentが既存Route、Candidate、Contextへ到達するRepository fixture。"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from Context.Selection.project_context_inputs import derive_context_inputs
from Context.Manifest.build_context_manifest import build as build_context_manifest
from ControlPlane.unity_agent_control_plane import UnityAgentControlPlane, validate_entry_request
from Orchestration.Routing.route_selector import load_routes, resolve_specialist, select_route, select_specialist_capability, task_fingerprint_from_intent
from Orchestration.ToolRouting.capability_request_builder import build_candidate_capability_requests, build_capability_requests, conditions_for_intent
from Runtime.ReferenceImplementation.performance_read_only import PerformancePilotContractError, verify_performance_read_only
from Runtime.Tooling.capability_resolver import ResolutionContext


ROOT = Path(__file__).resolve().parents[2]


class PerformanceEntryFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "Project"
        for folder in ("Assets", "Packages", "ProjectSettings"):
            (self.project / folder).mkdir(parents=True)
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.15f1\n", encoding="utf-8")
        self.snapshot = {"project": {"root": str(self.project), "exists": True, "identity_status": "bound", "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}, "build": {"requested_target": "Windows"}}

    def entry(self, symptom: str = "Main Thread frame time is high", *, comparison_requested: bool = False) -> dict:
        return {"schema_version": "2.0", "request_id": "performance-fixture", "entry_point": "codex_plugin", "project_root": str(self.project), "intent": {"kind": "performance_analysis", "symptom": symptom, "target_scope": "Scene/Main", "comparison_requested": comparison_requested}}

    def route_and_context(self, entry: dict, snapshot: dict | None = None):
        validate_entry_request(entry)
        environment = snapshot or self.snapshot
        fingerprint = task_fingerprint_from_intent(entry["intent"], environment, project_root=entry["project_root"], policy_allowed=True)
        route = select_route(fingerprint, load_routes(ROOT / "Orchestration/Routing/task-routes.yaml"))
        conditions = conditions_for_intent(entry["intent"], fingerprint)
        production = build_capability_requests(route_id=route["route_id"], project_root=entry["project_root"], active_conditions=conditions)
        candidate = build_candidate_capability_requests(route["route_id"], entry["project_root"], active_conditions=conditions)
        capability = select_specialist_capability(route["route_id"], production + candidate)
        inputs = derive_context_inputs(entry["project_root"], environment, entry["intent"])
        return fingerprint, route, conditions, production, candidate, capability, inputs

    def test_cpu_and_gpu_symptoms_use_performance_route_without_live_measurement(self) -> None:
        for symptom in ("Main Thread frame time is high", "GPU frame time is high after RendererFeature pass"):
            with self.subTest(symptom=symptom):
                entry = self.entry(symptom)
                fingerprint, route, conditions, production, candidate, capability, inputs = self.route_and_context(entry)
                self.assertEqual((fingerprint["artifact"], route["route_id"], capability), ("performance", "performance-experiment", "performance.analyze"))
                self.assertEqual(fingerprint["evidence_state"], "partial")
                self.assertEqual(conditions, {"project_fact_needed"})
                self.assertEqual([item["capability"] for item in production], ["project.inspect"])
                self.assertEqual([item["capability"] for item in candidate], ["performance.analyze"])
                self.assertEqual(inputs["specialist_tags"], {"performance"})
                facts = {(item["category"], item["key"]): item["value"] for item in inputs["specialist_items"]}
                self.assertEqual(facts[("task_fact", "performance_symptom")], symptom)
                self.assertEqual(facts[("task_fact", "requested_scope")], "Scene/Main")
                self.assertEqual(facts[("platform_fact", "requested_target")], "Windows")

    def test_graphics_correctness_and_performance_cost_are_separate(self) -> None:
        rendering = {"kind": "rendering_diagnosis", "symptom": "RendererFeature Pass does not execute", "target_scope": "Assets/Feature.cs"}
        fingerprint = task_fingerprint_from_intent(rendering, self.snapshot, project_root=str(self.project), policy_allowed=True)
        route = select_route(fingerprint, load_routes(ROOT / "Orchestration/Routing/task-routes.yaml"))
        self.assertEqual(route["route_id"], "rendering-incident")
        self.assertEqual(self.route_and_context(self.entry("RendererFeature Pass executes but GPU cost is high"))[1]["route_id"], "performance-experiment")

    def test_unknown_platform_and_comparison_request_are_not_invented(self) -> None:
        unknown = copy.deepcopy(self.snapshot)
        unknown["build"]["requested_target"] = "unknown"
        entry = self.entry(comparison_requested=True)
        *_, capability, inputs = self.route_and_context(entry, unknown)
        self.assertFalse(any(item["key"] == "requested_target" for item in inputs["specialist_items"]))
        self.assertTrue(all(item["tags"] == ["performance"] for item in inputs["specialist_items"]))
        self.assertIn("task_fact:analysis_mode", {f"{item['category']}:{item['key']}" for item in inputs["specialist_items"]})
        selection = resolve_specialist("performance-experiment", capability, unknown, pilot_enabled=True, context_items=inputs["specialist_items"])
        self.assertEqual(selection["reason_code"], "required_context_missing")

    def test_production_control_plane_blocks_unregistered_candidate(self) -> None:
        revisions = {name: "fixture-v1" for name in ("architecture_version", "policy_revision", "prompt_revision", "context_revision", "graph_revision", "runtime_profile_revision", "tool_schema_revision", "checkpoint_schema_revision", "evidence_schema_revision", "eval_contract_revision")}
        result = UnityAgentControlPlane(self.project.parent / "state").execute(self.entry(), environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True), executors={}, definition_fingerprint={"schema_version": "1.0", **revisions})
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Specialist unavailable: performance.analyze", result["reason"])

    def test_entry_to_context_receipt_and_static_performance_evidence(self) -> None:
        entry = self.entry("GPU frame time is high after RendererFeature pass")
        _, route, conditions, production, candidate, capability, inputs = self.route_and_context(entry)
        self.assertEqual((route["route_id"], [item["capability"] for item in candidate]), ("performance-experiment", ["performance.analyze"]))
        selection = resolve_specialist(route["route_id"], capability, self.snapshot, pilot_enabled=True, context_items=inputs["specialist_items"])
        self.assertEqual(selection["status"], "selected")
        manifest = build_context_manifest("performance-fixture", route["route_id"], project_facts=inputs["project_facts"], bindings=inputs["bindings"], capability_ids=[item["capability"] for item in production], active_conditions=conditions, specialist_selection=selection, specialist_items=inputs["specialist_items"], specialist_tags=inputs["specialist_tags"], required_specialist_keys=inputs["required_specialist_keys"])
        view = manifest["materialized_context"]
        transported = {"context_id": view["context_id"], "context_fingerprint": view["context_fingerprint"]["value"], "specialist_context": copy.deepcopy(view["specialist_context"])}
        metadata = {"measurement_source": "none", "unity_version": "6000.3.15f1", "platform": "Windows", "graphics_api": "unknown", "capture_mode": "none", "build_type": "unknown", "scene_or_scope": "Scene/Main", "measurement_window": "unknown", "known_limitations": ["No GPU timing capture"], "validity": "not_measured"}
        result = {"status": "completed", "profile_id": "performance_subagent", "capability": "performance.analyze", "confirmed_facts": ["User reports high GPU frame time"], "measurement_summary": {"metadata": metadata, "metrics": [], "baseline": None, "candidate": None, "delta": None}, "bottleneck_classification": "unknown", "hypotheses": ["RendererFeature may contribute to GPU cost"], "rejected_hypotheses": [], "required_observations": ["Capture GPU frame timing on target device"], "recommendations": ["Measure before changing Shader or RendererFeature"], "observed_evidence": [{"type": "performance_analysis", "source_ref": "fixture:performance-symptom", "observation": "Static analysis of user report only"}], "evidence_level": "static", "known_limitations": ["No live profiler, player, or target device result"], "received_context_id": view["context_id"], "received_context_fingerprint": view["context_fingerprint"]["value"], "runtime_evaluation": "NOT_EVALUATED_RUNTIME"}
        self.assertEqual(verify_performance_read_only(manifest, transported, result)["receipt_integrity"], "verified")
        with self.assertRaisesRegex(PerformancePilotContractError, "received"):
            verify_performance_read_only(manifest, transported, {**result, "received_context_fingerprint": "sha256:wrong"})

    def test_comparison_without_baseline_and_optimization_goal_do_not_apply(self) -> None:
        entry = self.entry("Optimize this heavy Shader", comparison_requested=True)
        fingerprint, route, _, production, _, capability, inputs = self.route_and_context(entry)
        self.assertEqual((route["route_id"], capability), ("performance-experiment", "performance.analyze"))
        self.assertEqual(fingerprint["evidence_state"], "baseline_required")
        self.assertEqual([item["operation_kind"] for item in production], ["read"])
        self.assertFalse(any(item["key"] == "baseline_reference" for item in inputs["specialist_items"]))
        self.assertEqual(next(item["value"] for item in inputs["specialist_items"] if item["key"] == "analysis_mode"), "comparison_requested")
        self.assertNotIn("performance.optimize", [capability])


if __name__ == "__main__":
    unittest.main()
