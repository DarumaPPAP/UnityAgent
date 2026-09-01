from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.Providers.UnityCli.command_builder import (
    build_pipeline_command,
    build_project_build_command,
    validate_safe_argv,
)
from Runtime.Tooling.Providers.UnityCli.discovery import discover_unity_cli_surface
from Runtime.Tooling.Providers.UnityCli.result_mapper import parse_json_sequence
from Runtime.Tooling.Providers.UnityCli.session import UnityCliNdjsonSession
from Runtime.Tooling.Providers.UnityCli.unity_cli_provider import UnityCliProvider


def envelope(command: str, data=None, *, success=True, errors=None) -> str:
    return json.dumps(
        {
            "success": success,
            "command": command,
            "data": data,
            "errors": errors or [],
            "warnings": [],
        }
    )


class FakeUnityCliDispatch:
    def __init__(
        self,
        *,
        supported=None,
        malformed_project=False,
        test_xml: str | None = '<test-run result="Passed" total="1" passed="1" failed="0" skipped="0" inconclusive="0" />',
        test_exit=0,
        create_build=True,
        permission_denied=False,
        failure_class: str | None = None,
        runtime_catalog=None,
    ) -> None:
        self.supported = set(supported or {"projects", "run", "test", "build", "status", "pipeline", "command", "shell"})
        self.malformed_project = malformed_project
        self.test_xml = test_xml
        self.test_exit = test_exit
        self.create_build = create_build
        self.permission_denied = permission_denied
        self.failure_class = failure_class
        self.calls = []
        self.runtime_catalog = runtime_catalog or [
            {"name": "runtime_status", "runtimeOnly": True},
            {"name": "eval", "runtimeOnly": True},
        ]

    def _outcome(self, returncode: int, stdout: str = "", stderr: str = ""):
        result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        if self.failure_class == "runtime_timeout":
            return {"status": "failed", "failure_class": "runtime_timeout", "result": result}
        if self.failure_class == "runtime_cancelled":
            return {"status": "cancelled", "failure_class": "runtime_cancelled", "result": result}
        if returncode != 0:
            return {"status": "failed", "failure_class": "runtime_protocol_failure", "result": result}
        return {"status": "passed", "failure_class": None, "result": result, "payload": stdout}

    def __call__(self, request, *, cancel_event=None):
        command = list(request.command)
        self.calls.append(command)
        if self.permission_denied and command[-1:] == ["--version"]:
            raise PermissionError("no execute")
        if command[-1:] == ["--version"]:
            return self._outcome(0, "1.0.0-beta.3\n")

        if command[-1:] == ["--help"]:
            name = command[-2]
            return self._outcome(0 if name in self.supported else 2, "")

        if len(command) > 1 and command[1:3] == ["projects", "info"]:
            if self.malformed_project:
                return self._outcome(0, "{broken-json")
            return self._outcome(0, envelope("projects info", {"path": command[3], "editorVersion": "6000.3.12f1"}))

        if len(command) > 1 and command[1] == "status":
            return self._outcome(0, envelope("status", [{"state": "ready", "project": str(request.cwd), "pid": 42}]))

        if len(command) > 2 and command[1:3] == ["pipeline", "list"]:
            return self._outcome(0, envelope("pipeline list", [{"projectPath": str(request.cwd), "status": "ready"}]))

        if len(command) > 1 and command[1] == "command":
            if "--runtime" in command and command[2].startswith("--"):
                return self._outcome(0, envelope("command", self.runtime_catalog))
            if len(command) > 2 and command[2].startswith("--"):
                catalog = [
                    {"name": "get_scene_hierarchy", "runtimeOnly": False},
                    {"name": "find_gameobjects", "runtimeOnly": False},
                    {"name": "eval", "runtimeOnly": False},
                    {"name": "delete_gameobject", "runtimeOnly": False},
                ]
                return self._outcome(0, envelope("command", catalog))
            name = command[2]
            return self._outcome(0, envelope(name, {"name": name, "ok": True}))

        if len(command) > 1 and command[1] == "run":
            stdout = json.dumps({"type": "progress", "command": "run", "message": "Starting Unity..."}) + "\n"
            stdout += envelope("run", {"editorExitCode": 0})
            return self._outcome(0, stdout)

        if len(command) > 1 and command[1] == "test":
            if "--output" in command and self.test_xml is not None:
                output = Path(command[command.index("--output") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(self.test_xml, encoding="utf-8")
            success = self.test_exit == 0
            return self._outcome(
                self.test_exit,
                envelope(
                    "test",
                    {"output": command[command.index("--output") + 1]},
                    success=success,
                    errors=[] if success else [{"code": "TEST_FAILED"}],
                ),
            )

        if len(command) > 1 and command[1] == "build":
            output = Path(command[command.index("--output-path") + 1])
            if self.create_build:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("build", encoding="utf-8")
            stdout = json.dumps({"type": "progress", "command": "build", "message": "Starting Unity..."}) + "\n"
            stdout += envelope("build", {"target": command[command.index("--target") + 1], "output": str(output)})
            return self._outcome(0, stdout)

        if len(command) > 1 and command[1:4] == ["shell", "--protocol", "ndjson"]:
            responses = []
            for line in (request.stdin_text or "").splitlines():
                frame = json.loads(line)
                if frame.get("type") == "shutdown":
                    break
                responses.append(
                    json.dumps(
                        {
                            "id": frame["id"],
                            "exitCode": 0,
                            "envelope": {
                                "success": True,
                                "command": frame["argv"][0],
                                "data": {"ok": True},
                                "errors": [],
                                "warnings": [],
                            },
                        }
                    )
                )
            return self._outcome(0, "\n".join(responses) + "\n")

        return self._outcome(2, envelope("unknown", None, success=False, errors=[{"code": "UNKNOWN_COMMAND"}]))


class UnityCliProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "Project"
        (self.project / "Assets").mkdir(parents=True)
        (self.project / "Packages").mkdir()
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.3.12f1\n",
            encoding="utf-8",
        )
        self.cli = Path(self.tmp.name) / "unity"
        self.cli.write_text("", encoding="utf-8")
        self.temp_root = Path(self.tmp.name) / "RuntimeTemp"

    def snapshot(self, *, cli=True, pipeline=True, test_framework=True, build_module=True, safe_mode=False, running=False) -> dict:
        return {
            "schema_version": "1.0",
            "project": {"root": str(self.project.resolve()), "exists": True, "identity_status": "bound", "unity_version": "6000.3.12f1", "required_paths": {"assets": True, "packages": True, "project_settings": True}},
            "filesystem": {"readable": True, "writable": True, "writable_in_mutation_scope": "unknown"},
            "git": {"available": True, "repository_bound": True},
            "unity_editor": {"installed": True, "version": "6000.3.12f1", "executable_path": None, "project_version_match": True, "running": running, "safe_mode": safe_mode, "project_bound": False, "binding_status": "unbound" if running else "not_running", "bound_instance_id": None},
            "unity_cli": {"available": cli, "version": "1.0.0-beta.3" if cli else None, "executable_path": str(self.cli.resolve()) if cli else None, "failure_class": None if cli else "unavailable"},
            "pipeline": {"installed": pipeline, "reachable": pipeline},
            "myunitymcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
            "coplay_mcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
            "test_framework": {"available": test_framework},
            "build": {"requested_target": "StandaloneWindows64", "requested_target_module_available": build_module},
            "player_runtime": {"reachable": False, "instance_id": None},
            "profile_hint": "CLI_ONLY" if cli else "NATIVE_EDITOR",
            "binding_fingerprint": "0" * 64,
        }

    def request(self, capability: str) -> dict:
        operation = {"project.build": "build"}.get(capability, "read")
        evidence = {
            "project.inspect": ["project_fact"],
            "compile.observe": ["compile_observation"],
            "project.test": ["test_execution"],
            "project.build": ["build_execution"],
            "scene.inspect": ["editor_observation"],
        }[capability]
        return {
            "schema_version": "1.0",
            "capability": capability,
            "project_root": str(self.project.resolve()),
            "operation_kind": operation,
            "required_evidence": evidence,
            "mutation_scope": None,
            "approval_ref": None,
            "preferred_surface": "editor",
        }

    def provider(self, dispatch, *, snapshot=None, build_methods=None, player_commands=None):
        return UnityCliProvider(
            self.project,
            snapshot or self.snapshot(),
            dispatch_fn=dispatch,
            allowed_build_methods=set(build_methods or ()),
            allowed_player_commands=set(player_commands or ()),
            temp_root=self.temp_root,
        )

    def test_cli_absence_is_normal_unavailable_and_does_not_install(self) -> None:
        fake = FakeUnityCliDispatch()
        provider = self.provider(fake, snapshot=self.snapshot(cli=False))
        self.assertEqual(provider.available_capabilities(), frozenset())
        self.assertEqual(fake.calls, [])

    def test_permission_denied_is_unhealthy_not_exception(self) -> None:
        discovery = discover_unity_cli_surface(
            self.project,
            self.snapshot(),
            dispatch_fn=FakeUnityCliDispatch(permission_denied=True),
        )
        self.assertEqual(discovery.status, "unhealthy")
        self.assertEqual(discovery.failure_class, "permission_denied")

    def test_editor_status_is_observed_from_structured_output(self) -> None:
        discovery = discover_unity_cli_surface(
            self.project,
            self.snapshot(),
            dispatch_fn=FakeUnityCliDispatch(),
        )
        self.assertIsInstance(discovery.editor_status, list)
        self.assertEqual(discovery.editor_status[0]["state"], "ready")

    def test_malformed_json_does_not_become_project_fact(self) -> None:
        provider = self.provider(FakeUnityCliDispatch(malformed_project=True))
        self.assertNotIn("project.inspect", provider.available_capabilities())
        result = provider.run_project_inspect(self.request("project.inspect"), policy_allowed=True)
        self.assertEqual(result["failure_class"], "not_observed")

    def test_version_drift_missing_command_is_unsupported(self) -> None:
        fake = FakeUnityCliDispatch(supported={"projects", "run", "test", "status", "pipeline", "command", "shell"})
        provider = self.provider(fake, build_methods={"Builder.PerformBuild"})
        result = provider.run_build(
            self.request("project.build"),
            timeout_seconds=10,
            policy_allowed=True,
            execute_method="Builder.PerformBuild",
            build_output_relative_path="Build/Game.exe",
        )
        self.assertEqual(result["failure_class"], "unsupported")

    def test_pipeline_absence_does_not_expose_live_editor_capability(self) -> None:
        provider = self.provider(FakeUnityCliDispatch(), snapshot=self.snapshot(pipeline=False))
        self.assertNotIn("scene.inspect", provider.available_capabilities())

    def test_safe_mode_blocks_test(self) -> None:
        provider = self.provider(FakeUnityCliDispatch(), snapshot=self.snapshot(safe_mode=True, running=True))
        result = provider.run_tests(
            self.request("project.test"),
            run_id="safe-mode",
            timeout_seconds=10,
            policy_allowed=True,
        )
        self.assertEqual(result["failure_class"], "precondition_failed")

    def test_structured_test_failure_is_not_infrastructure_failure(self) -> None:
        xml = '<test-run result="Failed" total="2" passed="1" failed="1" skipped="0" inconclusive="0" />'
        provider = self.provider(FakeUnityCliDispatch(test_xml=xml, test_exit=6))
        result = provider.run_tests(
            self.request("project.test"),
            run_id="test-fail",
            timeout_seconds=10,
            policy_allowed=True,
        )
        self.assertEqual(result["failure_class"], "observed_test_failure")
        self.assertEqual(result["evidence"], ["test_execution"])

    def test_missing_test_xml_is_infrastructure_not_observed(self) -> None:
        provider = self.provider(FakeUnityCliDispatch(test_xml=None, test_exit=6))
        result = provider.run_tests(
            self.request("project.test"),
            run_id="test-infra",
            timeout_seconds=10,
            policy_allowed=True,
        )
        self.assertEqual(result["failure_class"], "execution_failed")
        self.assertEqual(result["evidence"], [])

    def test_timeout_and_cancel_preserve_execution_control_taxonomy(self) -> None:
        timeout = self.provider(FakeUnityCliDispatch(failure_class="runtime_timeout")).run_compile(
            self.request("compile.observe"),
            timeout_seconds=1,
            policy_allowed=True,
        )
        self.assertEqual(timeout["failure_class"], "timeout")
        cancelled = self.provider(FakeUnityCliDispatch(failure_class="runtime_cancelled")).run_compile(
            self.request("compile.observe"),
            timeout_seconds=10,
            policy_allowed=True,
        )
        self.assertEqual(cancelled["failure_class"], "cancelled")

    def test_raw_eval_and_secret_flags_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "raw mutation/eval"):
            build_pipeline_command(self.cli, self.project, "eval", ["return 1;"])
        with self.assertRaisesRegex(ValueError, "secret-bearing"):
            validate_safe_argv(["unity", "auth", "login", "--client-secret", "literal-secret"])

    def test_scene_inspect_uses_dynamic_read_only_allowlist(self) -> None:
        provider = self.provider(FakeUnityCliDispatch())
        result = provider.run_scene_inspect(
            self.request("scene.inspect"),
            command_name="get_scene_hierarchy",
            timeout_seconds=10,
            policy_allowed=True,
        )
        self.assertEqual(result["status"], "passed")
        blocked = provider.run_scene_inspect(
            self.request("scene.inspect"),
            command_name="delete_gameobject",
            timeout_seconds=10,
            policy_allowed=True,
        )
        self.assertEqual(blocked["failure_class"], "blocked_by_policy")

    def test_build_requires_repository_allowlisted_method_and_never_auto_installs(self) -> None:
        fake = FakeUnityCliDispatch()
        provider = self.provider(fake, build_methods={"Builder.PerformBuild"})
        result = provider.run_build(
            self.request("project.build"),
            timeout_seconds=10,
            policy_allowed=True,
            execute_method="Builder.PerformBuild",
            build_output_relative_path="Build/Game.exe",
        )
        self.assertEqual(result["status"], "passed")
        build_calls = [call for call in fake.calls if len(call) > 1 and call[1] == "build"]
        self.assertTrue(build_calls)
        self.assertFalse(any("--allow-install" in call for call in build_calls))
        denied = provider.run_build(
            self.request("project.build"),
            timeout_seconds=10,
            policy_allowed=True,
            execute_method="Generated.Run",
            build_output_relative_path="Build/Game.exe",
        )
        self.assertEqual(denied["failure_class"], "unsupported")

    def test_ndjson_session_uses_pretokenized_requests_and_redacts(self) -> None:
        fake = FakeUnityCliDispatch()
        session = UnityCliNdjsonSession(self.cli, self.project, dispatch_fn=fake)
        result = session.run([["projects", "info", str(self.project)]], timeout_seconds=10)
        self.assertEqual(result["status"], "passed")
        shell_call = next(call for call in fake.calls if len(call) > 1 and call[1] == "shell")
        self.assertIn("--protocol", shell_call)

    def test_player_transport_only_returns_runtime_allowlisted_commands_without_evidence(self) -> None:
        provider = self.provider(FakeUnityCliDispatch(), player_commands={"runtime_status"})
        result = provider.discover_player_transport(runtime_name="MyGame", timeout_seconds=10)
        self.assertEqual(result["status"], "passed")
        self.assertEqual([item["name"] for item in result["commands"]], ["runtime_status"])
        self.assertEqual(result["evidence"], [])

    def test_json_sequence_rejects_malformed_ndjson(self) -> None:
        with self.assertRaises(ValueError):
            parse_json_sequence('{"success":true}\nnot-json\n')

    def test_builder_keeps_windows_paths_as_single_argv_items(self) -> None:
        command = build_project_build_command(
            r"C:\Program Files\Unity CLI\unity.exe",
            r"C:\Work Projects\My Game",
            build_target="StandaloneWindows64",
            execute_method="Builder.PerformBuild",
            output_path=r"C:\Work Projects\My Game\Build\Game.exe",
        )
        self.assertIn(r"C:\Program Files\Unity CLI\unity.exe", command.argv)
        self.assertIn(r"C:\Work Projects\My Game", command.argv)
        self.assertFalse(any(item.startswith('"') or item.endswith('"') for item in command.argv))


if __name__ == "__main__":
    unittest.main()
