"""Read-only observation and evidence tests against the real File Provider."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from unityagent.runtime.evidence_capture.tool_runtime_evidence import observation_payload
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider


class ReadSmokeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="unityagent-smoke-read-")
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / "Project"
        (self.project / "Assets").mkdir(parents=True)
        (self.project / "Packages").mkdir()
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.3.12f1\n", encoding="utf-8"
        )
        (self.project / "Assets/Example.cs").write_text("class Example {}\n", encoding="utf-8")
        self.provider = FileProvider(self.project)

    def request(self, capability, *, project=None):
        return {
            "schema_version": "1.0",
            "capability": capability,
            "project_root": str(project or self.project),
            "operation_kind": "read",
            "required_evidence": ["source_read"] if capability == "source.read" else ["project_fact"],
            "mutation_scope": None,
            "approval_ref": None,
            "preferred_surface": "project",
        }

    def test_source_read_returns_actual_content_with_evidence(self):
        result = self.provider.read_text(
            self.request("source.read"), relative_path="Assets/Example.cs", policy_allowed=True
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["content"], "class Example {}\n")
        self.assertEqual(result["evidence"], ["source_read"])

    def test_disallowed_read_produces_no_evidence(self):
        result = self.provider.read_text(
            self.request("source.read"), relative_path="Assets/Example.cs", policy_allowed=False
        )
        self.assertEqual(result["failure_class"], "blocked_by_policy")
        self.assertEqual(result["evidence"], [])

    def test_wrong_project_never_reads_file(self):
        result = self.provider.read_text(
            self.request("source.read", project=self.project / "Other"),
            relative_path="Assets/Example.cs",
            policy_allowed=True,
        )
        self.assertEqual(result["failure_class"], "scope_violation")
        self.assertEqual(result["evidence"], [])

    def test_missing_file_does_not_claim_read_success(self):
        result = self.provider.read_text(
            self.request("source.read"), relative_path="Assets/Missing.cs", policy_allowed=True
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["evidence"], [])

    def test_serialized_project_info_is_scoped_and_not_runtime_truth(self):
        (self.project / "ProjectSettings/GraphicsSettings.asset").write_text(
            "GraphicsSettings:\n  m_CustomRenderPipeline: {fileID: 0}\n", encoding="utf-8"
        )
        (self.project / "ProjectSettings/QualitySettings.asset").write_text(
            "QualitySettings:\n  m_QualitySettings:\n  - customRenderPipeline: {fileID: 0}\n", encoding="utf-8"
        )
        result = self.provider.inspect_project(self.request("project.inspect"), policy_allowed=True)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["render_pipeline"], "builtin")
        self.assertEqual(result["runtime_evaluation"], "NOT_EVALUATED_RUNTIME")
        self.assertEqual(result["evidence"], ["project_fact"])

    def test_incomplete_project_settings_are_not_guessed(self):
        (self.project / "ProjectSettings/GraphicsSettings.asset").write_text(
            "GraphicsSettings:\n  m_CustomRenderPipeline: {fileID: 0}\n", encoding="utf-8"
        )
        result = self.provider.inspect_project(self.request("project.inspect"), policy_allowed=True)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["render_pipeline"], "unknown")

    def test_evidence_projection_removes_raw_logs_and_secrets(self):
        request = self.request("source.read")
        result = {
            "status": "passed", "provider_ref": "file", "evidence": ["source_read"],
            "received_context_id": "ctx-1", "path": "Assets/Example.cs",
            "content": "class Example {}", "stdout": "raw transport",
            "metadata": {"api_token": "private"},
        }
        payload = observation_payload(request, result)
        self.assertNotIn("stdout", payload["result"])
        self.assertEqual(payload["result"]["metadata"]["api_token"], "***")
        self.assertEqual(result["metadata"]["api_token"], "private")

    def test_mutation_is_not_reinterpreted_as_read_evidence(self):
        request = self.request("source.read")
        request["operation_kind"] = "source_mutation"
        with self.assertRaisesRegex(ValueError, "read"):
            observation_payload(request, {
                "status": "passed", "provider_ref": "file", "evidence": ["source_read"]
            })


if __name__ == "__main__":
    unittest.main()
