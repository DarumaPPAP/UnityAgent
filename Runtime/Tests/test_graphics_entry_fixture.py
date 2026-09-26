"""実Unity動作を主張しないEntryからStatic Evidenceまでの一体Fixture。"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from Context.Manifest.build_context_manifest import build as build_context_manifest
from Context.Selection.project_context_inputs import derive_context_inputs
from ControlPlane.unity_agent_control_plane import UnityAgentControlPlane, validate_entry_request
from Orchestration.Routing.route_selector import load_routes, resolve_specialist, select_route, task_fingerprint_from_intent
from Orchestration.Routing.route_selector import select_specialist_capability
from Orchestration.ToolRouting.capability_request_builder import build_capability_requests, build_candidate_capability_requests, conditions_for_intent
from Runtime.ReferenceImplementation.graphics_read_only import GraphicsPilotContractError, verify_graphics_read_only
from Runtime.Tooling.capability_resolver import ResolutionContext


ROOT = Path(__file__).resolve().parents[2]


class GraphicsEntryFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "Project"
        for folder in ("Assets", "Packages", "ProjectSettings"):
            (self.project / folder).mkdir(parents=True)
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.15f1\n", encoding="utf-8")
        (self.project / "ProjectSettings/GraphicsSettings.asset").write_text("fixture-render-pipeline: urp\n", encoding="utf-8")
        (self.project / "Assets/Example.shader").write_text("Shader \"Example\" { SubShader { Pass {} } }\n", encoding="utf-8")
        self.environment = {"project": {"root": str(self.project), "exists": True, "identity_status": "bound", "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}, "build": {"requested_target": "Windows"}}

    def entry(self, *, change_requested: bool = False) -> dict:
        return {"schema_version": "2.0", "request_id": "graphics-fixture", "entry_point": "codex_plugin", "project_root": str(self.project), "intent": {"kind": "rendering_diagnosis", "symptom": "Shader Pass is not visible", "target_scope": "Assets/Example.shader", "change_requested": change_requested}}

    def observed(self, category: str, key: str, value: str, source: Path) -> dict:
        return {"category": category, "key": key, "value": value, "source": str(source), "revision": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(), "freshness": {"status": "current", "checked_at_attempt": 1}, "observed_at_attempt": 1, "tags": ["rendering"], "required": True}

    def prepare(self, *, change_requested: bool = False, include_pipeline: bool = True, pilot_enabled: bool = True, environment: dict | None = None):
        request = self.entry(change_requested=change_requested)
        validate_entry_request(request)
        snapshot = environment or self.environment
        fingerprint = task_fingerprint_from_intent(request["intent"], snapshot, project_root=request["project_root"], policy_allowed=True)
        route = select_route(fingerprint, load_routes(ROOT / "Orchestration/Routing/task-routes.yaml"))
        self.assertEqual(route["route_id"], "rendering-incident")
        conditions = conditions_for_intent(request["intent"], fingerprint)
        requests = build_capability_requests(route_id=route["route_id"], project_root=request["project_root"], active_conditions=conditions)
        self.assertTrue(requests)
        self.assertTrue(all(item["operation_kind"] == "read" for item in requests))
        inputs = derive_context_inputs(request["project_root"], snapshot, request["intent"])
        if include_pipeline:
            inputs["specialist_items"].append(self.observed("project_fact", "render_pipeline", "urp", self.project / "ProjectSettings/GraphicsSettings.asset"))
        inputs["specialist_items"].append(self.observed("project_fact", "relevant_source", "Assets/Example.shader", self.project / "Assets/Example.shader"))
        candidate_requests = build_candidate_capability_requests(route["route_id"], request["project_root"], active_conditions=conditions)
        selected_capability = select_specialist_capability(route["route_id"], requests + candidate_requests)
        selection = resolve_specialist(route["route_id"], selected_capability, snapshot, pilot_enabled=pilot_enabled, requested_mutation=change_requested, context_items=inputs["specialist_items"])
        return request, route, requests, inputs, selection

    def test_entry_to_context_receipt_and_static_evidence(self) -> None:
        request, route, requests, inputs, selection = self.prepare()
        self.assertEqual(selection["status"], "selected")
        manifest = build_context_manifest("graphics-fixture", route["route_id"], project_facts=inputs["project_facts"], bindings=inputs["bindings"], capability_ids=[item["capability"] for item in requests], active_conditions={"project_fact_needed"}, specialist_selection=selection, specialist_items=inputs["specialist_items"], specialist_tags=inputs["specialist_tags"], required_specialist_keys=inputs["required_specialist_keys"])
        view = manifest["materialized_context"]
        self.assertEqual(view["specialist_context"]["profile_id"], "graphics_subagent")
        self.assertEqual(view["specialist_context"]["capability"], "graphics.diagnose")
        transported = {"context_id": view["context_id"], "context_fingerprint": view["context_fingerprint"]["value"], "specialist_context": copy.deepcopy(view["specialist_context"])}
        result = {"status": "completed", "profile_id": "graphics_subagent", "capability": "graphics.diagnose", "confirmed_facts": ["Fixture shader contains a Pass"], "hypotheses": ["Renderer asset may omit the pass"], "rejected_hypotheses": [], "required_observations": ["Editor Frame Debugger"], "proposed_diff": None, "required_approval": "none", "observed_evidence": [{"type": "source_read", "source_ref": "Assets/Example.shader", "observation": "Fixture source contains Pass"}, {"type": "graphics_diagnosis", "source_ref": "Assets/Example.shader", "observation": "Static diagnosis only"}], "evidence_level": "static", "known_limitations": ["No Editor or Player observation"], "received_context_id": view["context_id"], "received_context_fingerprint": view["context_fingerprint"]["value"], "runtime_evaluation": "NOT_EVALUATED_RUNTIME"}
        report = verify_graphics_read_only(manifest, transported, result)
        self.assertEqual(report["receipt_integrity"], "verified")
        self.assertEqual(report["runtime_evaluation"], "NOT_EVALUATED_RUNTIME")
        forged = {**result, "received_context_id": "ctx-forged"}
        with self.assertRaisesRegex(GraphicsPilotContractError, "received"):
            verify_graphics_read_only(manifest, transported, forged)

    def test_missing_context_pilot_disabled_and_unsupported_version(self) -> None:
        self.assertEqual(self.prepare(include_pipeline=False)[4]["reason_code"], "required_context_missing")
        self.assertEqual(self.prepare(pilot_enabled=False)[4]["reason_code"], "pilot_disabled")
        old = copy.deepcopy(self.environment)
        old["project"]["unity_version"] = "2022.3.62f1"
        self.assertEqual(resolve_specialist("rendering-incident", "graphics.diagnose", old, pilot_enabled=True)["reason_code"], "unity_version_unsupported")

    def test_production_entry_fails_closed_while_candidate_pilot_is_disabled(self) -> None:
        plane = UnityAgentControlPlane(self.project.parent / "state")
        revisions = {name: "fixture-v1" for name in ("architecture_version", "policy_revision", "prompt_revision", "context_revision", "graph_revision", "runtime_profile_revision", "tool_schema_revision", "checkpoint_schema_revision", "evidence_schema_revision", "eval_contract_revision")}
        result = plane.execute(self.entry(), environment_snapshot=self.environment, context=ResolutionContext(policy_allowed=True), executors={}, definition_fingerprint={"schema_version": "1.0", **revisions})
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Specialist unavailable: graphics.diagnose", result["reason"])

    def test_mutation_task_keeps_graphics_analysis_read_only(self) -> None:
        request, route, requests, inputs, selection = self.prepare(change_requested=True)
        self.assertTrue(request["intent"]["change_requested"])
        self.assertEqual((route["entry_action"], selection["status"]), ("investigate", "selected"))
        self.assertTrue(all(item["operation_kind"] == "read" for item in requests))
        self.assertNotIn("provider_id", selection)
        manifest = build_context_manifest("graphics-change-fixture", route["route_id"], project_facts=inputs["project_facts"], bindings=inputs["bindings"], specialist_selection=selection, specialist_items=inputs["specialist_items"], specialist_tags=inputs["specialist_tags"], required_specialist_keys=inputs["required_specialist_keys"])
        view = manifest["materialized_context"]
        transported = {"context_id": view["context_id"], "context_fingerprint": view["context_fingerprint"]["value"], "specialist_context": copy.deepcopy(view["specialist_context"])}
        result = {"status": "completed", "profile_id": "graphics_subagent", "capability": "graphics.diagnose", "confirmed_facts": ["Fixture source contains Pass"], "hypotheses": [], "rejected_hypotheses": [], "required_observations": ["Editor compile"], "proposed_diff": "Proposed shader diff; not applied", "required_approval": "required_before_apply", "observed_evidence": [{"type": "graphics_diagnosis", "source_ref": "Assets/Example.shader", "observation": "Static review"}], "evidence_level": "static", "known_limitations": ["Apply not performed"], "received_context_id": view["context_id"], "received_context_fingerprint": view["context_fingerprint"]["value"], "runtime_evaluation": "NOT_EVALUATED_RUNTIME"}
        self.assertEqual(verify_graphics_read_only(manifest, transported, result)["status"], "fixture_contract_verified")


if __name__ == "__main__":
    unittest.main()
