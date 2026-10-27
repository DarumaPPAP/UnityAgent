"""Connection contracts: capability registry and structured Unity CLI response."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from unityagent.runtime.tooling.provider_contract import load_provider_registry
from unityagent.runtime.tooling.provider_registry import RuntimeProviderRegistry
from unityagent.runtime.tooling.providers.unity_cli.command_builder import (
    build_project_info_command,
    build_status_command,
    validate_safe_argv,
)
from unityagent.runtime.tooling.providers.unity_cli.result_mapper import (
    classify_cli_failure,
    normalize_project_info,
    parse_json_sequence,
    terminal_envelope,
)


class ConnectionSmokeTests(unittest.TestCase):
    def test_current_registry_exposes_connection_and_read_capabilities(self):
        contract = load_provider_registry()
        self.assertIn("unity_cli", contract.providers)
        self.assertIn("file", contract.providers)
        self.assertIn("project.inspect", contract.capability_requirements)
        self.assertIn("scene.inspect", contract.capability_requirements)

    def test_doctor_uses_existing_installer_registration(self):
        registry = RuntimeProviderRegistry(registry=load_provider_registry())
        self.assertEqual([item.provider_id for item in registry.management_candidates("doctor")], ["installer"])

    def test_project_info_command_binds_explicit_project(self):
        with tempfile.TemporaryDirectory() as directory:
            request = build_project_info_command("unity", directory)
            self.assertIn(str(Path(directory)), request.argv)
            self.assertEqual(request.argv[1:3], ("projects", "info"))
            self.assertEqual(request.argv[3], str(Path(directory)))

    def test_editor_status_command_binds_project(self):
        with tempfile.TemporaryDirectory() as directory:
            request = build_status_command("unity", directory)
            self.assertIn("--project-path", request.argv)
            self.assertIn(str(Path(directory)), request.argv)

    def test_cli_project_info_requires_structured_success(self):
        output = json.dumps({"success": True, "command": "projects info", "data": {
            "path": "/fixture/Project", "editorVersion": "6000.3.12f1"
        }, "errors": []})
        result = normalize_project_info(exit_code=0, stdout=output)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["project"]["editorVersion"], "6000.3.12f1")
        self.assertEqual(result["evidence"], ["project_fact"])

    def test_malformed_cli_json_never_becomes_observed_project(self):
        result = normalize_project_info(exit_code=0, stdout="{bad-json")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["evidence"], [])

    def test_missing_cli_project_data_is_not_observed(self):
        result = normalize_project_info(exit_code=0, stdout=json.dumps({
            "success": True, "command": "projects info", "data": None, "errors": []
        }))
        self.assertEqual(result["failure_class"], "not_observed")
        self.assertEqual(result["evidence"], [])

    def test_unavailable_timeout_and_unsupported_are_distinct(self):
        for code, dispatcher, expected in (
            (7, None, "unavailable"),
            (124, "runtime_timeout", "timeout"),
            (2, None, "unsupported"),
        ):
            with self.subTest(code=code):
                self.assertEqual(
                    classify_cli_failure(exit_code=code, envelope=None, dispatcher_failure_class=dispatcher)[0],
                    expected,
                )

    def test_duplicate_ndjson_keys_fail_closed_in_strict_mode(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON member"):
            parse_json_sequence('{"success":true,"success":true}', strict=True)

    def test_progress_log_alone_does_not_prove_connection(self):
        self.assertIsNone(terminal_envelope(parse_json_sequence('{"type":"progress","message":"ready"}')))

    def test_command_args_reject_shell_injection_capability(self):
        with self.assertRaises(ValueError):
            validate_safe_argv(["unity", "--client-secret", "secret"])


if __name__ == "__main__":
    unittest.main()
