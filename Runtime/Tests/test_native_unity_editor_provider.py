from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.Environment.native_editor_discovery import EditorProcessObservation
from Runtime.Tooling.Providers.NativeUnityEditor.native_unity_editor_provider import NativeUnityEditorProvider
from Runtime.Tooling.Providers.NativeUnityEditor.process_builder import build_compile_command, build_execute_method_command


class FakeUnityDispatch:
    def __init__(self, *, log_text: str = "", returncode: int = 0, test_xml: str | None = None, create_build_output: bool = True, failure_class: str | None = None, cancelled: bool = False) -> None:
        self.log_text = log_text
        self.returncode = returncode
        self.test_xml = test_xml
        self.create_build_output = create_build_output
        self.failure_class = failure_class
        self.cancelled = cancelled

    def __call__(self, request, *, cancel_event=None):
        command = list(request.command)
        if "-logFile" in command:
            log_path = Path(command[command.index("-logFile") + 1])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(self.log_text, encoding="utf-8")
        if "-testResults" in command and self.test_xml is not None:
            Path(command[command.index("-testResults") + 1]).write_text(self.test_xml, encoding="utf-8")
        if "-build" in command and self.create_build_output:
            output = Path(command[command.index("-build") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("build", encoding="utf-8")
        result = SimpleNamespace(returncode=self.returncode, stdout="", stderr="")
        if self.cancelled:
            return {"status": "cancelled", "failure_class": "runtime_cancelled", "result": result}
        if self.failure_class:
            return {"status": "failed", "failure_class": self.failure_class, "result": result}
        if self.returncode != 0:
            return {"status": "failed", "failure_class": "runtime_protocol_failure", "result": result}
        return {"status": "passed", "failure_class": None, "result": result, "payload": ""}


class NativeUnityEditorProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "Project"
        (self.project / "Assets").mkdir(parents=True)
        (self.project / "Packages").mkdir()
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.12f1\n", encoding="utf-8")
        self.editor = Path(self.tmp.name) / "Unity Editor With Spaces.exe"
        self.editor.write_text("", encoding="utf-8")
        self.runtime_temp = Path(self.tmp.name) / "RuntimeTemp"

    def snapshot(self, *, editor_path: Path | None = None, test_framework=True, build_module=True, safe_mode=False, running=False, binding_status="not_running") -> dict:
        executable = editor_path if editor_path is not None else self.editor
        return {
            "schema_version": "1.0",
            "project": {"root": str(self.project.resolve()), "exists": True, "identity_status": "bound", "unity_version": "6000.3.12f1", "required_paths": {"assets": True, "packages": True, "project_settings": True}},
            "filesystem": {"readable": True, "writable": True, "writable_in_mutation_scope": "unknown"},
            "git": {"available": True, "repository_bound": True},
            "unity_editor": {"installed": True, "version": "6000.3.12f1", "executable_path": str(executable.resolve()), "project_version_match": True, "running": running, "safe_mode": safe_mode, "project_bound": running and binding_status == "bound", "binding_status": binding_status, "bound_instance_id": "pid:42" if running and binding_status == "bound" else None},
            "unity_cli": {"available": False, "version": None, "executable_path": None, "failure_class": "unavailable"},
            "pipeline": {"installed": False, "reachable": False},
            "myunitymcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
            "coplay_mcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
            "test_framework": {"available": test_framework},
            "build": {"requested_target": "StandaloneWindows64", "requested_target_module_available": build_module},
            "player_runtime": {"reachable": False, "instance_id": None},
            "profile_hint": "NATIVE_EDITOR",
            "binding_fingerprint": "0" * 64,
        }

    def request(self, capability: str) -> dict:
        operation_kind = "build" if capability == "project.build" else "read"
        evidence = {"compile.observe": ["compile_observation"], "project.test": ["test_execution"], "project.build": ["build_execution"]}[capability]
        return {"schema_version": "1.0", "capability": capability, "project_root": str(self.project.resolve()), "operation_kind": operation_kind, "required_evidence": evidence, "mutation_scope": None, "approval_ref": None, "preferred_surface": "editor"}

    def provider(self, dispatch, *, snapshot=None, process_probe=None) -> NativeUnityEditorProvider:
        return NativeUnityEditorProvider(self.project, snapshot or self.snapshot(), dispatch_fn=dispatch, process_probe_fn=process_probe or (lambda *, cwd: []), editor_candidates=[], temp_root=self.runtime_temp)

    def test_compile_success_produces_compile_evidence_only(self) -> None:
        result = self.provider(FakeUnityDispatch()).run_compile(self.request("compile.observe"), run_id="compile-pass", timeout_seconds=10, policy_allowed=True)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["evidence"], ["compile_observation"])

    def test_compiler_error_is_not_treated_as_pass_even_with_exit_zero(self) -> None:
        result = self.provider(FakeUnityDispatch(log_text="Assets/Foo.cs(10,5): error CS1002: ; expected\n")).run_compile(self.request("compile.observe"), run_id="compile-error", timeout_seconds=10, policy_allowed=True)
        self.assertEqual(result["failure_class"], "execution_failed")
        self.assertEqual(result["diagnostics"][0]["code"], "CS1002")

    def test_test_xml_failure_is_observed_test_failure(self) -> None:
        xml = '<test-run result="Failed" total="2" passed="1" failed="1" skipped="0" inconclusive="0" />'
        result = self.provider(FakeUnityDispatch(test_xml=xml)).run_tests(self.request("project.test"), run_id="tests-failed", timeout_seconds=10, policy_allowed=True)
        self.assertEqual(result["failure_class"], "observed_test_failure")

    def test_test_xml_pass_is_normalized(self) -> None:
        xml = '<test-run result="Passed" total="2" passed="2" failed="0" skipped="0" inconclusive="0" />'
        result = self.provider(FakeUnityDispatch(test_xml=xml)).run_tests(self.request("project.test"), run_id="tests-pass", timeout_seconds=10, policy_allowed=True)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["test_result"]["passed"], 2)

    def test_missing_test_xml_is_not_observed(self) -> None:
        result = self.provider(FakeUnityDispatch()).run_tests(self.request("project.test"), run_id="tests-no-xml", timeout_seconds=10, policy_allowed=True)
        self.assertEqual(result["failure_class"], "not_observed")

    def test_missing_editor_executable_is_unavailable(self) -> None:
        missing = Path(self.tmp.name) / "MissingUnity.exe"
        result = self.provider(FakeUnityDispatch(), snapshot=self.snapshot(editor_path=missing)).run_compile(self.request("compile.observe"), run_id="missing-editor", timeout_seconds=10, policy_allowed=True)
        self.assertEqual(result["failure_class"], "unavailable")

    def test_existing_same_project_editor_blocks_second_editor(self) -> None:
        process = EditorProcessObservation(pid=42, executable_path=str(self.editor), command_line=f'"{self.editor}" -projectPath "{self.project}"', project_root=str(self.project), safe_mode=False)
        result = self.provider(FakeUnityDispatch(), process_probe=lambda *, cwd: [process]).run_compile(self.request("compile.observe"), run_id="locked-project", timeout_seconds=10, policy_allowed=True)
        self.assertEqual(result["failure_class"], "precondition_failed")

    def test_build_module_must_be_observed_available(self) -> None:
        result = self.provider(FakeUnityDispatch(), snapshot=self.snapshot(build_module=False)).run_build(self.request("project.build"), run_id="build-no-module", timeout_seconds=10, policy_allowed=True, build_output_relative_path="Builds/Game.exe")
        self.assertEqual(result["failure_class"], "unsupported")

    def test_successful_build_requires_output_observation(self) -> None:
        result = self.provider(FakeUnityDispatch()).run_build(self.request("project.build"), run_id="build-pass", timeout_seconds=10, policy_allowed=True, build_output_relative_path="Builds/Game.exe")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["evidence"], ["build_execution"])

    def test_safe_mode_blocks_test(self) -> None:
        result = self.provider(FakeUnityDispatch(), snapshot=self.snapshot(safe_mode=True)).run_tests(self.request("project.test"), run_id="safe-mode-tests", timeout_seconds=10, policy_allowed=True)
        self.assertEqual(result["failure_class"], "precondition_failed")

    def test_timeout_and_cancel_use_execution_control_taxonomy(self) -> None:
        timeout_result = self.provider(FakeUnityDispatch(returncode=124, failure_class="runtime_timeout")).run_compile(self.request("compile.observe"), run_id="compile-timeout", timeout_seconds=1, policy_allowed=True)
        self.assertEqual(timeout_result["failure_class"], "timeout")
        cancel_result = self.provider(FakeUnityDispatch(cancelled=True)).run_compile(self.request("compile.observe"), run_id="compile-cancel", timeout_seconds=10, policy_allowed=True)
        self.assertEqual(cancel_result["failure_class"], "cancelled")

    def test_windows_paths_remain_single_unquoted_argv_items(self) -> None:
        executable = Path(r"C:\Program Files\Unity\Editor\Unity.exe")
        project = Path(r"C:\Work Projects\My Game")
        log = Path(r"C:\Temp Logs\compile.log")
        command = build_compile_command(executable_path=executable, project_root=project, log_path=log).command
        self.assertIn(str(executable), command)
        self.assertIn(str(project), command)
        self.assertFalse(any(item.startswith('"') or item.endswith('"') for item in command))

    def test_execute_method_is_fail_closed_without_repository_allowlist(self) -> None:
        with self.assertRaisesRegex(ValueError, "not repository-allowlisted"):
            build_execute_method_command(executable_path=self.editor, project_root=self.project, log_path=self.runtime_temp / "execute.log", method_name="GeneratedArbitraryCode.Run")


if __name__ == "__main__":
    unittest.main()
