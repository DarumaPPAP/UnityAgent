from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

import yaml

from unityagent.runtime.tooling.providers.unity_artist_cli.command_builder import ARTIST_COMMANDS, build_artist_command
from unityagent.runtime.tooling.providers.unity_artist_cli.result_mapper import normalize_artist_result
from unityagent.runtime.tooling.providers.unity_cli.command_builder import build_pipeline_command


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "artist-cutover-baseline.json"


class ArtistCutoverBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_nine_internal_commands_and_three_public_operations_are_distinct(self):
        cases = self.baseline["commands"]
        self.assertEqual({case["command"] for case in cases}, ARTIST_COMMANDS)
        registration = (ROOT / "subagent/artist_subagent/tools/editor/Editor/Pipeline/ArtistPipelineCommandRegistration.cs").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'\[CliCommand\("artist\.([a-z]+)"', registration)), ARTIST_COMMANDS)
        manifest = yaml.safe_load((ROOT / "subagent/artist_subagent/manifest.yaml").read_text(encoding="utf-8"))
        public = {f'{capability["id"]}.{operation}' for capability in manifest["capabilities"] for operation in capability["operations"]}
        self.assertEqual(public, {"artist.camera.inspect", "artist.camera.refine", "visual.capture"})
        self.assertEqual(manifest["identity"]["id"], "artist_subagent")
        self.assertEqual(manifest["installation"], {"mode": "optional", "required": False, "auto_install": False})

    def test_golden_inputs_keep_typed_argv_and_project_binding(self):
        project = str(ROOT.resolve())
        for case in self.baseline["commands"]:
            with self.subTest(case=case["id"]):
                arguments = case["arguments"]
                host = build_artist_command("unity-artist", project, case["command"], arguments, timeout_seconds=17)
                pipeline = build_pipeline_command("unity", project, f'artist.{case["command"]}', case["pipeline_arguments"])
                self.assertEqual(host.command, ["unity-artist", case["command"], "--project-path", project, *case["pipeline_arguments"], "--format", "json", "--non-interactive", "--no-banner"])
                self.assertEqual(pipeline.argv, ("unity", "command", f'artist.{case["command"]}', "--project-path", project, *case["pipeline_arguments"], "--format", "json", "--non-interactive", "--no-banner"))
                self.assertEqual(host.cwd, ROOT.resolve())
                self.assertEqual(host.timeout_seconds, 17)
                self.assertTrue(host.expect_json)

    def test_golden_success_preserves_editor_payload_and_current_evidence(self):
        for case in self.baseline["commands"]:
            with self.subTest(case=case["id"]):
                editor = case["editor_result"]
                data = {"provider": {"data": {"result": json.dumps(editor)}}}
                result = normalize_artist_result({"status": "passed", "data": data}, command=case["command"])
                self.assertEqual(result["status"], "passed")
                self.assertEqual(result["provider_ref"], "unity_artist_cli")
                self.assertEqual(result["command_id"], editor["command"])
                self.assertEqual(result["payload"], data)
                self.assertEqual(result["evidence"], case["current_evidence"])
                self.assertNotIn("human_visual_acceptance", result["evidence"])

    def test_golden_outer_failures_preserve_code_and_emit_no_success_evidence(self):
        for case in self.baseline["failures"]:
            with self.subTest(code=case["code"]):
                result = normalize_artist_result({"status": "blocked", "errors": [{"code": case["code"], "message": "fixture rejection"}]}, command="apply")
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["failure_class"], case["failure_class"])
                self.assertEqual(result["error_code"], case["code"])
                self.assertEqual(result["evidence"], [])

    def test_receipt_is_backend_reported_and_not_inferred_from_command(self):
        expected = self.baseline["context_receipt"]
        result = normalize_artist_result({"status": "passed", "data": {"contextReceipt": expected}}, command="inspect")
        self.assertEqual(result["received_context_id"], expected["receivedContextId"])
        self.assertEqual(result["received_context_fingerprint"], expected["receivedContextFingerprint"])
        missing = normalize_artist_result({"status": "passed", "data": {}}, command="inspect")
        self.assertNotIn("received_context_id", missing)
        self.assertNotIn("received_context_fingerprint", missing)

    def test_fixture_cannot_be_used_as_live_editor_or_performance_evidence(self):
        self.assertEqual(self.baseline["provenance"]["kind"], "source_derived_synthetic_contract")
        self.assertEqual(self.baseline["provenance"]["source_revision"], "84eade0868c403b440a4d7db86b21cfa98c731a0")
        self.assertEqual(self.baseline["observations"], {
            "unity_compile": "BLOCKED_NOT_RUN", "editor_read_only": "BLOCKED_NOT_RUN",
            "editor_mutation": "BLOCKED_NOT_RUN", "without_legacy_host": "BLOCKED_NOT_RUN",
            "visual_acceptance": "not_observed", "performance": "not_observed",
        })

    def test_domain_workflow_floor_cannot_be_lowered_to_enable_cutover(self):
        registry = yaml.safe_load((ROOT / "src/unityagent/runtime/tooling/provider_registry.yaml").read_text(encoding="utf-8"))
        self.assertEqual(registry["capability_requirements"]["domain.workflow"], {
            "minimum_safety_strength": 5, "minimum_evidence_strength": 5,
        })

    def test_source_derived_results_preserve_revision_approval_diff_and_diagnostics(self):
        for case in self.baseline["commands"]:
            with self.subTest(case=case["id"]):
                result = case["editor_result"]
                command = case["command"]
                self.assertEqual(result["baseRevision"], "revision-before")
                self.assertTrue(result["undoAvailable"])
                planned = command in {"plan", "preview", "apply", "refine"} or command == "cinematic" and case["arguments"]["--operation"] != "inspect"
                self.assertEqual(result["approvalRequired"], planned)
                if planned:
                    self.assertTrue(result["planId"])
                    self.assertTrue(result["exactDiff"])
                if command in {"plan", "preview", "refine"}:
                    self.assertIn("camera_binding", result["evidence"])
                if command == "capture":
                    self.assertTrue(any(item.startswith("color_path:") for item in result["evidence"]))
                    self.assertIn("depth_channel:not_configured", result["evidence"])
                    self.assertIn("object_id_channel:not_configured", result["evidence"])
                if command == "evaluate":
                    self.assertIn("review_decision:needs_refine", result["evidence"])
                    self.assertIn("review_notes_present", result["evidence"])

    def test_unallowlisted_commands_and_options_never_build_transport(self):
        for command in ("eval", "eval_file", "shell", "save", "gameobject", "artist.apply", "apply --save"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                build_artist_command("unity-artist", ROOT, command)
        for option in ("--runtime", "--project-path", "--eval", "--save", "--shell"):
            with self.subTest(option=option), self.assertRaises(ValueError):
                build_artist_command("unity-artist", ROOT, "inspect", {option: "value"})


if __name__ == "__main__":
    unittest.main()
