"""Public startup and project binding smoke tests (no Unity Editor required)."""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from unityagent import cli
from unityagent.runtime.tooling.environment.project_identity import (
    observe_project_identity,
    read_project_version,
    resolve_project_root,
    same_project_root,
)


class BootstrapSmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="unityagent-smoke-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "Project"
        (self.project / "Assets").mkdir(parents=True)
        (self.project / "Packages").mkdir()
        (self.project / "Packages/manifest.json").write_text('{"dependencies":{}}', encoding="utf-8")
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.3.12f1\n", encoding="utf-8"
        )

    def test_public_cli_main_is_available(self):
        self.assertTrue(callable(cli.main))

    def test_doctor_parses_explicit_project(self):
        with patch.object(sys, "argv", ["unity-agent", "doctor", "--project-p", str(self.project)]):
            args = cli._parse_args()
        self.assertTrue(same_project_root(args.project_path, self.project))

    def test_setup_defaults_to_plan_not_mutation(self):
        with patch.object(sys, "argv", ["unity-agent", "setup", "--project-p", str(self.project)]):
            args = cli._parse_args()
        self.assertEqual(args.operation, "plan")

    def test_nested_directory_resolves_owner_project(self):
        self.assertTrue(same_project_root(resolve_project_root(cwd=self.project / "Assets"), self.project))

    def test_explicit_foreign_or_nonproject_path_does_not_fall_back(self):
        with self.assertRaisesRegex(ValueError, "Invalid Unity Project"):
            resolve_project_root(self.root / "Other", cwd=self.project)

    def test_missing_project_manifest_is_rejected(self):
        (self.project / "Packages/manifest.json").unlink()
        with self.assertRaisesRegex(ValueError, "Invalid Unity Project"):
            resolve_project_root(self.project)

    def test_project_version_is_observed_not_guessed(self):
        self.assertEqual(read_project_version(self.project), "6000.3.12f1")
        observed = observe_project_identity(self.project)
        self.assertEqual(observed["unity_version"], "6000.3.12f1")
        self.assertEqual(observed["identity_status"], "bound")
        (self.project / "ProjectSettings/ProjectVersion.txt").unlink()
        self.assertIsNone(read_project_version(self.project))
        self.assertIsNone(observe_project_identity(self.project)["unity_version"])

    def test_blank_explicit_project_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "blank"):
            resolve_project_root("")


if __name__ == "__main__":
    unittest.main()
