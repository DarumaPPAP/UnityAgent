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
from Runtime.Contracts.runtime_handoff import validate_runtime_handoff
from Runtime.ExecutionControl.process_runtime import StreamingProcessResult
from Runtime.Handoff.reasoning_runtime import build_reasoning_request
from Runtime.ReferenceImplementation.world_planning import WorldPlanContractError
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Runner.Codex import codex_runner

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

    def execute(self, *, stale: bool = False, mutate: bool = False, semantic_invalid: bool = False, write_attempt: bool = False, original_mutation: bool = False, output_missing: bool = False):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = list(command)
            workspace = Path(command[command.index("--cd") + 1])
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
            response = plane.execute(self.entry, environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True), executors={}, definition_fingerprint=fingerprint(), specialist_pilot_enabled=True, reasoning_model="gpt-fixture", reasoning_command_prefix=["codex"])
        return response, plane, captured

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
