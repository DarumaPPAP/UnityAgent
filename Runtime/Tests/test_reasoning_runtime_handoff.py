"""EntryからControlled Codex processまでのProviderless reasoning契約。"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator
from jsonschema import ValidationError
from referencing import Registry, Resource

from ControlPlane.unity_agent_control_plane import UnityAgentControlPlane, validate_entry_request
from Context.Manifest.build_context_manifest import build as build_context_manifest
from Context.Selection.project_context_inputs import derive_context_inputs
from Runtime.Contracts.runtime_handoff import validate_runtime_handoff
from Runtime.ExecutionControl.process_runtime import StreamingProcessResult
from Runtime.Handoff.reasoning_runtime import build_reasoning_request
from Runtime.ReferenceImplementation.world_planning import WorldPlanContractError
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.tool_broker import ToolBroker
from Runtime.Tooling.Environment.discovery import discover_environment
from Runtime.Tooling.Environment.environment_snapshot import UnityCliSnapshot
from Orchestration.Routing.route_selector import resolve_specialist
from Runtime.Runner.Codex import codex_runner
from Runtime.Tooling.Providers.UnityCli.profiler_observation import normalize_profiler_observation

ROOT = Path(__file__).resolve().parents[2]


def fingerprint() -> dict:
    revisions = {name: "reasoning-fixture" for name in ("architecture_version", "policy_revision", "prompt_revision", "context_revision", "graph_revision", "runtime_profile_revision", "tool_schema_revision", "checkpoint_schema_revision", "evidence_schema_revision", "eval_contract_revision")}
    return {"schema_version": "1.0", **revisions}


def process_result() -> StreamingProcessResult:
    return StreamingProcessResult(returncode=0, stdout="", stderr="", timed_out=False, cancelled=False, root_pid=1, process_tree_cleanup="not_required", remaining_processes=0, duration_seconds=0.01, first_output_latency_seconds=None, event_count=0, last_event_timestamp=None)


class ReadOnlyBroker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def dispatch(self, request, *args, **kwargs):
        self.calls.append(request["capability"])
        return {"status": "completed"}


class ReasoningRuntimeHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "Project"
        for name in ("Assets", "Packages", "ProjectSettings"):
            (self.project / name).mkdir(parents=True)
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.15f1\n", encoding="utf-8")
        self.snapshot = {"project": {"root": str(self.project), "exists": True, "identity_status": "bound", "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}, "build": {"requested_target": "unknown"}}
        self.entry = {"schema_version": "2.0", "request_id": "reasoning-fixture", "entry_point": "codex_plugin", "project_root": str(self.project), "intent": {"kind": "world_planning", "world_goal": "Plan a dungeon", "scene_scope": "Assets/Scenes/Dungeon"}}
        self.broker = ReadOnlyBroker()

    def artifact(self, command: list[str], *, stale: bool = False, mutate: bool = False, semantic_invalid: bool = False) -> dict:
        workspace = Path(command[command.index("--cd") + 1])
        context = json.loads((workspace / "specialist-context.json").read_text(encoding="utf-8"))
        facts = {item["key"]: item["value"] for item in context["specialist_context"]["items"] if item["type"] == "task_fact"}
        plan = {"world_goal": facts["world_goal"], "scene_scope": facts["requested_scope"], "environment_type": None, "visual_intent": None, "zones": ["entrance", "chambers"], "camera_requirements": ["Review camera framing"], "lighting_requirements": ["Define lighting direction"], "content_requirements": ["List required assets"], "technical_constraints": ["Preserve existing architecture"], "performance_constraints": ["Set budget after platform decision"], "platform_constraints": [], "prohibited_changes": [], "acceptance_criteria": ["Human reviews the plan"], "work_packages": [{"id": "layout", "goal": "Define traversable zones", "scope": "Dungeon", "domain_hint": "generic_unity", "depends_on": [], "constraints": ["Preserve authored content"], "acceptance_criteria": ["Reviewable layout"], "required_evidence": ["static_review"]}], "dependencies": [], "required_evidence": ["world_plan"], "open_decisions": ["environment_type unknown", "desired_mood unknown", "target_platform unknown"], "human_review_required": True, "direct_unity_mutation": False, "automatic_visual_acceptance": False}
        if mutate:
            plan["direct_unity_mutation"] = True
        if semantic_invalid:
            plan["open_decisions"] = []
        return {"status": "completed", "profile_id": "world_creator_subagent", "capability": "world.plan", "execution_mode": "planning_only", "provider_resolution": "not_required", "source_context_id": context["context_id"], "source_context_fingerprint": "sha256:stale" if stale else context["context_fingerprint"], "world_plan": plan, "evidence_level": "runtime_reasoning", "known_limitations": ["Editor, Player and target device are not observed"], "runtime_evaluation": "RUNTIME_OBSERVED"}

    def execute(self, *, stale: bool = False, mutate: bool = False, semantic_invalid: bool = False, write_attempt: bool = False, original_mutation: bool = False, output_missing: bool = False, executors=None):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = list(command)
            workspace = Path(command[command.index("--cd") + 1])
            captured["context"] = json.loads((workspace / "specialist-context.json").read_text(encoding="utf-8"))
            if write_attempt:
                (workspace / "unwanted.txt").write_text("write attempt", encoding="utf-8")
            if original_mutation:
                (self.project / "Assets" / "unwanted.asset").write_text("original mutation", encoding="utf-8")
            if not output_missing:
                artifact = self.artifact(command, stale=stale, mutate=mutate, semantic_invalid=semantic_invalid)
                Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(artifact), encoding="utf-8")
            return process_result()

        plane = UnityAgentControlPlane(self.root / "state", broker=self.broker)
        with patch.object(codex_runner, "run_streaming_process", side_effect=fake_run):
            response = plane.execute(self.entry, environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True), executors=executors or {}, definition_fingerprint=fingerprint(), specialist_pilot_enabled=True, reasoning_model="gpt-fixture", reasoning_command_prefix=["codex"])
        return response, plane, captured

    def test_required_observation_reaches_reasoning_with_durable_context_binding(self):
        self.broker = ToolBroker()
        self.snapshot = discover_environment(str(self.project), editor_candidates=[], editor_candidates_observed=True, editor_processes=[], editor_processes_observed=True, unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"), provider_instances={"myunitymcp": [], "coplay_mcp": []}, which_fn=lambda _: None).to_dict()
        def selection(*args, **kwargs):
            return {**resolve_specialist(*args, **kwargs), "required_observation_capabilities": ["project.inspect"]}
        executor = lambda *_: {"status": "passed", "provider_ref": "file", "evidence": ["project_fact"], "observed_marker": "fixture-only-fact", "stdout": "excluded process log"}
        with patch("ControlPlane.unity_agent_control_plane.resolve_specialist", side_effect=selection):
            response, plane, captured = self.execute(executors={"file": executor})
        self.assertEqual(response["status"], "completed", response)
        items = captured["context"]["specialist_context"]["items"]
        observations = [item for item in items if item["key"] == "observation:project.inspect"]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["value"]["result"], {"observed_marker": "fixture-only-fact"})
        self.assertEqual(observations[0]["source"], "evidence:" + response["evidence_refs"][0])
        proof = json.loads((plane.state_store.layout.root / response["orchestration_decision_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(proof["observation_evidence_refs"], [response["evidence_refs"][0]])
        before = json.loads((plane.state_store.layout.root / proof["previous_context_manifest_ref"]).read_text(encoding="utf-8"))
        self.assertNotEqual(before["materialized_context"]["context_fingerprint"]["value"], captured["context"]["context_fingerprint"])
        self.assertEqual(captured["context"]["context_fingerprint"], response["handoff"]["context_fingerprint"])

    def test_required_observation_without_durable_evidence_blocks_reasoning(self):
        def selection(*args, **kwargs):
            return {**resolve_specialist(*args, **kwargs), "required_observation_capabilities": ["project.inspect"]}
        with patch("ControlPlane.unity_agent_control_plane.resolve_specialist", side_effect=selection):
            response, _, captured = self.execute()
        self.assertEqual(response["status"], "blocked")
        self.assertNotIn("command", captured)
        self.assertIn("required observation", response["results"][-1]["runtime_failure"]["reason"])

    def test_unverified_or_over_budget_observation_cannot_start_reasoning(self):
        self.broker = ToolBroker()
        self.snapshot = discover_environment(str(self.project), editor_candidates=[], editor_candidates_observed=True, editor_processes=[], editor_processes_observed=True, unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"), provider_instances={"myunitymcp": [], "coplay_mcp": []}, which_fn=lambda _: None).to_dict()
        def selection(*args, **kwargs):
            return {**resolve_specialist(*args, **kwargs), "required_observation_capabilities": ["project.inspect"]}
        cases = [([], "small", "verified"), (["project_fact"], "x" * 300000, "budget")]
        for evidence, observation, reason in cases:
            with self.subTest(reason=reason), patch("ControlPlane.unity_agent_control_plane.resolve_specialist", side_effect=selection):
                executor = lambda *_: {"status": "passed", "provider_ref": "file", "evidence": evidence, "observation": observation}
                response, _, captured = self.execute(executors={"file": executor})
                self.assertEqual(response["status"], "blocked")
                self.assertNotIn("command", captured)
                self.assertIn(reason, response["results"][-1]["runtime_failure"]["reason"].lower())

    def test_entry_to_durable_reasoning_plan_keeps_context_and_original_workspace(self):
        response, plane, captured = self.execute()
        self.assertEqual(response["status"], "completed", response)
        self.assertEqual(self.broker.calls, ["project.inspect"])
        self.assertEqual(response["handoff"]["runtime_action"]["kind"], "specialist_reasoning")
        self.assertEqual(response["handoff"]["route_id"], "world-creation")
        self.assertEqual(response["handoff"]["execution_profile"], "generic_planning")
        self.assertEqual(response["handoff"]["runtime_action"]["profile_id"], "world_creator_subagent")
        self.assertEqual(response["handoff"]["runtime_action"]["capability"], "world.plan")
        self.assertEqual(response["handoff"]["mutation_scope"], {})
        self.assertNotIn("provider_ref", response["handoff"]["runtime_action"])
        self.assertEqual(captured["command"][captured["command"].index("--sandbox") + 1], "read-only")
        self.assertIn("--output-schema", captured["command"])
        outcome = response["results"][-1]
        self.assertEqual(outcome["capability"], "world.plan")
        artifact = json.loads((plane.state_store.layout.root / outcome["artifact_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(artifact["source_context_id"], response["handoff"]["context_id"])
        self.assertEqual(artifact["source_context_fingerprint"], response["handoff"]["context_fingerprint"])
        evidence = plane.evidence_store.verify_record(outcome["evidence_ref"], expected_run_id=response["run_id"])
        self.assertEqual(evidence["verification_status"], "passed")
        execution = json.loads((plane.state_store.layout.root / outcome["execution_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(execution["original_workspace_changed_paths"], [])
        self.assertEqual(execution["sandbox_mode"], "read-only")
        self.assertEqual(execution["source_context_id"], response["handoff"]["context_id"])
        self.assertEqual(execution["source_context_fingerprint"], response["handoff"]["context_fingerprint"])
        self.assertEqual((execution["reasoning_provenance"]["profile_id"], execution["reasoning_provenance"]["capability"]), ("world_creator_subagent", "world.plan"))
        self.assertEqual(execution["reasoning_provenance"]["model_revision"], "not_observed")
        self.assertIn("metrics.json", execution["telemetry_refs"])
        schema_paths = [ROOT / "Runtime/Contracts/execution-result.schema.yaml", ROOT / "Runtime/Contracts/runtime-failure.schema.yaml", ROOT / "Persistence/Contracts/definition-fingerprint.schema.yaml"]
        schemas = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in schema_paths]
        registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas)
        Draft202012Validator(schemas[0], registry=registry).validate(execution)

    def test_performance_observation_reaches_reasoning_as_limited_measurement(self):
        snapshot = discover_environment(str(self.project), editor_candidates=[], editor_candidates_observed=True, editor_processes=[], editor_processes_observed=True, unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"), provider_instances={"myunitymcp": [], "coplay_mcp": []}, which_fn=lambda _: None).to_dict()
        editor_path = self.root / "Unity.exe"
        cli_path = self.root / "unity.exe"
        editor_path.write_text("fixture", encoding="utf-8")
        cli_path.write_text("fixture", encoding="utf-8")
        snapshot["unity_editor"].update(installed=True, version="6000.3.15f1", executable_path=str(editor_path), project_version_match=True, running=True, safe_mode=False, project_bound=True, binding_status="bound", bound_instance_id="editor-fixture")
        snapshot["unity_cli"].update(available=True, version="1.0.0-beta.10", executable_path=str(cli_path), failure_class=None)
        snapshot["pipeline"].update(installed=True, reachable=True)
        snapshot["build"]["requested_target"] = "StandaloneWindows64"
        stats = {"render": {"drawCalls": 4, "batches": 3, "setPassCalls": 2, "triangles": 8, "vertices": 12}, "memory": {"totalAllocatedBytes": 1048576, "totalReservedBytes": 2097152, "monoUsedBytes": 1024, "monoHeapBytes": 2048}, "frameTiming": {"available": False, "cpuFrameTimeMs": 0, "cpuMainThreadFrameTimeMs": 0, "gpuFrameTimeMs": 0}}
        observation = normalize_profiler_observation(stats, unity_version="6000.3.15f1")
        calls = []

        def file_executor(request, _context, _arguments):
            calls.append(request["capability"])
            return {"status": "passed", "provider_ref": "file", "evidence": ["project_fact"], "unity_version": "6000.3.15f1", "render_pipeline": "builtin"}

        def profiler_executor(request, _context, _arguments):
            calls.append(request["capability"])
            return {"status": "passed", "provider_ref": "unity_cli", "evidence": ["profiler_observation"], **observation}

        def fake_run(command, **kwargs):
            workspace = Path(command[command.index("--cd") + 1])
            context = json.loads((workspace / "specialist-context.json").read_text(encoding="utf-8"))
            observed = next(item for item in context["specialist_context"]["items"] if item["key"] == "observation:profiler.observe")
            capture = observed["value"]["result"]["measurements"][0]
            artifact = {"status": "completed", "profile_id": "performance_subagent", "capability": "performance.analyze", "execution_mode": "read_only_analysis", "provider_resolution": "not_required", "source_context_id": context["context_id"], "source_context_fingerprint": context["context_fingerprint"], "confirmed_facts": [], "hypotheses": [], "rejected_hypotheses": [], "required_observations": ["Collect controlled multi-frame Player timing"], "known_limitations": capture["metadata"]["known_limitations"], "mutation_performed": False, "evidence_level": "runtime_reasoning", "runtime_evaluation": "RUNTIME_OBSERVED", "measurements": [{"source_ref": observed["source"], **capture}], "bottleneck_classification": "unknown", "classification_basis": [], "comparison": None, "recommendations": ["Measure on the target device before classification"]}
            Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(artifact), encoding="utf-8")
            return process_result()

        entry = {"schema_version": "2.0", "request_id": "performance-fixture", "entry_point": "codex_plugin", "project_root": str(self.project), "intent": {"kind": "performance_analysis", "symptom": "GPU frame time is high", "target_scope": "Scene/Main"}}
        plane = UnityAgentControlPlane(self.root / "performance-state")
        with patch.object(codex_runner, "run_streaming_process", side_effect=fake_run):
            response = plane.execute(entry, environment_snapshot=snapshot, context=ResolutionContext(policy_allowed=True), executors={"file": file_executor, "unity_cli": profiler_executor}, definition_fingerprint=fingerprint(), reasoning_model="gpt-fixture", reasoning_command_prefix=["codex"])
        self.assertEqual(response["status"], "completed", response)
        self.assertEqual(calls, ["project.inspect", "profiler.observe"])
        records = [plane.evidence_store.verify_record(ref) for ref in response["evidence_refs"]]
        self.assertEqual([record["verification_status"] for record in records], ["passed", "passed", "passed"])
        self.assertEqual([record["completion"] for record in records[:2]], ["verified", "verified"])
        inputs = derive_context_inputs(str(self.project), snapshot, entry["intent"])
        mutation_context = build_context_manifest("performance-mutation-fixture", "performance-experiment", project_facts=inputs["project_facts"], bindings=inputs["bindings"], capability_ids=["profiler.observe"], active_conditions={"mutation_requested"})
        self.assertIn("binding:baseline_capture_or_explicit_missing_baseline", mutation_context["unresolved_bindings"])
        self.assertIn("binding:quality_settings", mutation_context["unresolved_bindings"])

    def test_stale_context_semantic_failure_and_empty_output_fail_closed(self):
        cases = [({"stale": True}, "context_binding_failed"), ({"mutate": True}, "structured_output_invalid"), ({"semantic_invalid": True}, "world_plan_contract_failed"), ({"output_missing": True}, "structured_output_invalid"), ({"write_attempt": True}, "mutation_attempt_detected"), ({"original_mutation": True}, "mutation_attempt_detected")]
        for options, failure_class in cases:
            with self.subTest(options=options):
                self.broker.calls.clear()
                response, plane, _ = self.execute(**options)
                self.assertEqual(response["status"], "blocked")
                self.assertEqual(response["results"][-1]["status"], "blocked")
                self.assertEqual(response["results"][-1]["runtime_failure"]["failure_class"], failure_class)
                self.assertEqual(plane.evidence_store.verify_record(response["results"][-1]["evidence_ref"])["verification_status"], "failed")

    def test_runner_unavailable_is_durable_failure(self):
        plane = UnityAgentControlPlane(self.root / "state", broker=self.broker)
        response = plane.execute(self.entry, environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True), executors={}, definition_fingerprint=fingerprint(), specialist_pilot_enabled=True)
        self.assertEqual(response["status"], "blocked")
        outcome = response["results"][-1]
        self.assertEqual(outcome["runtime_failure"]["failure_class"], "runner_unavailable")
        self.assertEqual(plane.evidence_store.verify_record(outcome["evidence_ref"])["verification_status"], "failed")
        with patch("Runtime.Handoff.reasoning_runtime._command_prefix", side_effect=codex_runner.CodexRunnerError("Codex CLI was not found on PATH")):
            response = plane.execute(self.entry, environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True), executors={}, definition_fingerprint=fingerprint(), specialist_pilot_enabled=True, reasoning_model="gpt-fixture")
        self.assertEqual(response["results"][-1]["runtime_failure"]["failure_class"], "runner_unavailable")

    def test_runtime_profile_blocks_project_access_and_direct_mutation_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            workspace = base / "workspace"
            workspace.mkdir()
            schema = workspace / "schema.json"
            schema.write_text('{"type":"object","additionalProperties":false,"properties":{},"required":[]}', encoding="utf-8")
            request = {"schema_version": "1.0", "run_id": "run", "step_id": "step", "action_id": "action", "workspace_root": str(workspace), "original_workspace_root": str(self.project), "prompt": "plan", "execution": {"profile": "generic_planning", "work_kind": "analysis", "reasoning": True, "mutation_authorized": False}, "mutation_scope": {}, "output_schema_path": str(schema), "profile_id": "world_creator_subagent", "capability": "world.plan", "source_context_id": "ctx", "source_context_fingerprint": "sha256:fixture", "tool_identity": {"provider": "openai", "model": "gpt-fixture", "model_revision": "not_observed", "tool_manifest_hash": "not_applicable_reasoning_runtime"}, "definition_fingerprint": fingerprint()}
            for invalid in ({"project_access": "full_when_authorized", "direct_mutation": False}, {"project_access": "none", "direct_mutation": True}):
                with self.subTest(profile=invalid), patch.object(codex_runner, "_profile", return_value={**invalid, "allowed_work_kinds": ["analysis"]}), patch.object(codex_runner, "run_streaming_process", side_effect=AssertionError("process must not launch")):
                    with self.assertRaises(codex_runner.CodexRunnerError):
                        codex_runner.execute(request, base / "output", command_prefix=["codex"], timeout_seconds=5, reasoning_effort="high")
            project_output = self.project / "reasoning-output"
            with self.assertRaises(codex_runner.CodexRunnerError):
                codex_runner.execute(request, project_output, command_prefix=["codex"], timeout_seconds=5, reasoning_effort="high")
            self.assertFalse(project_output.exists())

    def test_handoff_rejects_provider_identity_and_mutation_scope(self):
        response, plane, _ = self.execute()
        handoff = copy.deepcopy(response["handoff"])
        handoff["runtime_action"]["provider_ref"] = "forged"
        with self.assertRaises(ValueError):
            validate_runtime_handoff(handoff)
        handoff = copy.deepcopy(response["handoff"])
        handoff["mutation_scope"] = {"allowed_paths": ["Assets"]}
        with self.assertRaises(ValueError):
            validate_runtime_handoff(handoff)
        manifest = json.loads((plane.state_store.layout.root / response["context_manifest_ref"]).read_text(encoding="utf-8"))
        handoff = copy.deepcopy(response["handoff"])
        handoff["context_fingerprint"] = "sha256:stale"
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ValueError):
            build_reasoning_request(handoff, manifest, original_project=self.project, workspace=Path(temporary) / "workspace", model="gpt-fixture")

    def test_entry_cannot_spoof_reasoning_authority(self):
        for key in ("execution_mode", "provider_resolution", "execution_profile", "runtime_action", "provider_id", "output_contract_ref"):
            entry = copy.deepcopy(self.entry)
            entry["intent"][key] = "forged"
            with self.subTest(key=key), self.assertRaises((ValidationError, ValueError)):
                validate_entry_request(entry)

    def test_original_project_cannot_host_reasoning_persistence(self):
        plane = UnityAgentControlPlane(self.project / ".unityagent-control", broker=self.broker)
        response = plane.execute(self.entry, environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True), executors={}, definition_fingerprint=fingerprint(), specialist_pilot_enabled=True, reasoning_model="gpt-fixture", reasoning_command_prefix=["codex"])
        self.assertEqual(response["status"], "blocked")
        self.assertIn("outside the original Project", response["reason"])
        self.assertEqual(self.broker.calls, [])


if __name__ == "__main__":
    unittest.main()
