"""Production catalogから実ToolBroker・Persistenceを通すControlled Reasoning fixture。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from tests.runtime.test_reasoning_runtime_handoff import fingerprint, process_result
from unityagent.runtime.runner.codex import codex_runner
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.environment.environment_snapshot import UnityCliSnapshot
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider
from unityagent.context.manifest.build_context_manifest import build as build_context_manifest
from unityagent.context.selection.project_context_inputs import derive_context_inputs


class GraphicsProductionReasoningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "Project"
        for folder in ("Assets", "Packages", "ProjectSettings"):
            (self.project / folder).mkdir(parents=True)
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.15f1\n", encoding="utf-8")
        (self.project / "Assets/A.shader").write_text('Shader "Fixture" { SubShader { Pass {} } }', encoding="utf-8")
        self.snapshot = discover_environment(str(self.project), editor_candidates=[], editor_candidates_observed=True, editor_processes=[], editor_processes_observed=True, unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"), provider_instances={"myunitymcp": [], "coplay_mcp": []}, which_fn=lambda _: None).to_dict()
        self.entry = {"schema_version": "2.0", "request_id": "graphics-production", "entry_point": "codex_plugin", "project_root": str(self.project), "intent": {"kind": "rendering_diagnosis", "symptom": "Pass missing", "target_scope": "Assets/A.shader", "change_requested": True}}

    def execute(self, pipeline):
        calls, captured = [], {}
        if pipeline == "builtin":
            (self.project / "ProjectSettings/GraphicsSettings.asset").write_text("GraphicsSettings:\n  m_CustomRenderPipeline: {fileID: 0}\n", encoding="utf-8")
            (self.project / "ProjectSettings/QualitySettings.asset").write_text("QualitySettings:\n  m_QualitySettings:\n  - customRenderPipeline: {fileID: 0}\n", encoding="utf-8")
        def executor(request, context, arguments):
            calls.append(request["capability"])
            if request["capability"] == "source.read":
                return FileProvider(self.project).read_text(request, relative_path="Assets/A.shader", policy_allowed=context.policy_allowed)
            self.assertEqual(request["capability"], "project.inspect")
            return FileProvider(self.project).inspect_project(request, policy_allowed=context.policy_allowed)

        def process(command, **kwargs):
            view = json.loads((Path(command[command.index("--cd") + 1]) / "specialist-context.json").read_text(encoding="utf-8"))
            captured["context"] = view
            observations = [item["source"] for item in view["specialist_context"]["items"] if item["key"].startswith("observation:")]
            artifact = {"status": "completed", "profile_id": "graphics_subagent", "capability": "graphics.diagnose", "execution_mode": "read_only_analysis", "provider_resolution": "not_required", "source_context_id": view["context_id"], "source_context_fingerprint": view["context_fingerprint"], "confirmed_facts": [], "hypotheses": ["Inspect render pass scheduling"], "rejected_hypotheses": [], "required_observations": ["Editor Frame Debugger"], "known_limitations": ["Controlled process fixture; no live reasoning or Unity verification"], "mutation_performed": False, "evidence_level": "runtime_reasoning", "runtime_evaluation": "RUNTIME_OBSERVED", "observation_refs": observations, "proposed_diff": "Proposed shader change, not applied", "required_approval": "required_before_apply"}
            Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(artifact), encoding="utf-8")
            return process_result()

        plane = UnityAgentControlPlane(self.root / "state")
        with patch.object(codex_runner, "run_streaming_process", side_effect=process) as runner:
            response = plane.execute(self.entry, environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True), executors={"file": executor}, definition_fingerprint=fingerprint(), reasoning_model="fixture-model", reasoning_command_prefix=["codex-fixture"])
        return response, calls, captured, runner.call_count

    def test_production_entry_observes_before_selecting_reasoning(self):
        before = (self.project / "Assets/A.shader").read_bytes()
        response, calls, captured, launches = self.execute("builtin")
        self.assertEqual(response["status"], "completed", response)
        self.assertEqual(set(calls), {"project.inspect", "source.read"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(launches, 1)
        self.assertEqual(response["handoff"]["runtime_action"]["capability"], "graphics.diagnose")
        self.assertEqual(captured["context"]["specialist_context"]["capability"], "graphics.diagnose")
        self.assertEqual((self.project / "Assets/A.shader").read_bytes(), before)
        self.assertEqual(len(response["evidence_refs"]), 3)

    def test_unknown_pipeline_blocks_after_observation_before_reasoning(self):
        response, calls, captured, launches = self.execute("unknown")
        self.assertEqual(set(calls), {"project.inspect", "source.read"})
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(launches, 0)
        self.assertIn("required_context_missing", response["results"][-1]["runtime_failure"]["reason"])

    def test_verification_and_apply_still_require_reproduction_bindings(self):
        inputs = derive_context_inputs(str(self.project), self.snapshot, self.entry["intent"])
        for condition in ("verification_requested", "mutation_requested"):
            manifest = build_context_manifest("reproduction-gate", "rendering-incident", project_facts=inputs["project_facts"], bindings=inputs["bindings"], active_conditions={condition})
            self.assertIn("binding:reproduction_conditions", manifest["materialized_context"]["unresolved_bindings"])
            self.assertIn("binding:renderer_feature_order", manifest["materialized_context"]["unresolved_bindings"])
            self.assertNotEqual(manifest["budget_report"]["decision"], "within_budget")


if __name__ == "__main__":
    unittest.main()
