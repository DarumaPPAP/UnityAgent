"""Host-only regression tests for the repository-owned Windows Full E2E harness."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

RUNNER = Path(__file__).resolve().parents[2] / "tools" / "full_e2e" / "run.py"
SPEC = importlib.util.spec_from_file_location("full_e2e_ci", RUNNER)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class FullE2ELocalRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name) / "repo"
        self.fixture = self.repo / "tests/unity/projects/production-e2e"
        self.package = self.repo / "Packages/com.darumappap.unity-agent"
        for folder in ("Assets", "Packages", "ProjectSettings"):
            (self.fixture / folder).mkdir(parents=True)
        (self.fixture / "Packages/manifest.json").write_text(json.dumps({
            "dependencies": {
                "com.darumappap.unity-agent": "file:../../../../../Packages/com.darumappap.unity-agent",
                "com.unity.render-pipelines.universal": "17.3.0",
            }}), encoding="utf-8")
        (self.fixture / "Assets/Editor").mkdir()
        (self.fixture / "Assets/Editor/probe.cs").write_text("class Probe {}", encoding="utf-8")
        (self.fixture / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.12f1\n", encoding="utf-8")
        self.package.mkdir(parents=True)
        template = b"class FullE2EProbe {}"
        (self.package / "Editor/Resources").mkdir(parents=True)
        (self.package / "Editor/Resources/FullE2EProbe.txt").write_bytes(template)
        (self.repo / "src/unityagent/control_plane/resources").mkdir(parents=True)
        (self.repo / "src/unityagent/control_plane/resources/FullE2EProbe.txt").write_bytes(template)
        self.workspace = Path(temporary.name) / "workspace"
        self.workspace.mkdir()

    def test_prepare_uses_repository_fixture_but_creates_isolated_project(self) -> None:
        project = HARNESS.prepare_workspace(self.repo, self.workspace)
        self.assertEqual(project, self.workspace / "p")
        manifest = json.loads((project / "Packages/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["dependencies"]["com.darumappap.unity-agent"],
                         "file:../../upm/com.darumappap.unity-agent")
        self.assertEqual(manifest["dependencies"]["com.unity.render-pipelines.universal"], "17.3.0")
        self.assertEqual((project / "Assets/Editor/probe.cs").read_text(encoding="utf-8"), "class Probe {}")
        self.assertEqual((self.workspace / "upm/com.darumappap.unity-agent/Editor/Resources/FullE2EProbe.txt").read_bytes(),
                         b"class FullE2EProbe {}")
        self.assertFalse((project / "Assets/UnityAgentE2E").exists())
        self.assertIn("../../../../../Packages", (self.fixture / "Packages/manifest.json").read_text(encoding="utf-8"))

    def test_rejects_template_mismatch_without_touching_source(self) -> None:
        (self.package / "Editor/Resources/FullE2EProbe.txt").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "templates disagree"):
            HARNESS.prepare_workspace(self.repo, self.workspace)

    def test_rejects_symlinked_fixture_input(self) -> None:
        try:
            (self.fixture / "Assets/link.cs").symlink_to(self.fixture / "Assets/Editor/probe.cs")
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks require special permissions on this Windows host")
        with self.assertRaisesRegex(RuntimeError, "Linked fixture"):
            HARNESS.prepare_workspace(self.repo, self.workspace)

    def test_plan_rejects_out_of_scope_mutation(self) -> None:
        plan = {"status": "planned", "plan_id": "a" * 64,
                "target_preimage": "absent", "approval_required": True,
                "exact_diff": [{"path": path, "operation": "create"} for path in HARNESS.EXPECTED_ASSETS]}
        HARNESS.review_plan(plan)
        plan["exact_diff"].append({"path": "Assets/Sensitive.asset", "operation": "create"})
        with self.assertRaisesRegex(RuntimeError, "unexpected mutations"):
            HARNESS.review_plan(plan)

    def test_requires_separate_explicit_human_approvals(self) -> None:
        with patch("builtins.input", return_value="yes"):
            with self.assertRaisesRegex(RuntimeError, "MUTATION approval"):
                HARNESS.require_confirmation("MUTATION", "a" * 64)
        with patch("builtins.input", return_value="MUTATION aaaaaaaa"):
            with self.assertRaisesRegex(RuntimeError, "SAVE approval"):
                HARNESS.require_confirmation("SAVE", "a" * 64)

    def test_revision_and_dirty_source_are_fail_closed(self) -> None:
        from subprocess import CompletedProcess
        with patch.object(HARNESS, "command", side_effect=[
            CompletedProcess([], 0, stdout="a" * 40 + "\n"),
            CompletedProcess([], 0, stdout=" M Packages/com.darumappap.unity-agent/package.json\n"),
        ]):
            with self.assertRaisesRegex(RuntimeError, "not clean"):
                HARNESS.git_source_revision(self.repo, "a" * 40)
        with patch.object(HARNESS, "command", return_value=CompletedProcess([], 0, stdout="a" * 40 + "\n")):
            with self.assertRaisesRegex(RuntimeError, "Revision mismatch"):
                HARNESS.git_source_revision(self.repo, "b" * 40)


if __name__ == "__main__":
    unittest.main()
