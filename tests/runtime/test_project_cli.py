"""公開CLIのProject検出と既存Plan Bindingの回帰。"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from unityagent import cli
from unityagent.runtime.tooling.environment import project_identity


def make_project(path):
    (path / "Assets").mkdir(parents=True)
    (path / "Packages").mkdir()
    (path / "Packages/manifest.json").write_text('{"dependencies":{}}')
    (path / "ProjectSettings").mkdir()
    (path / "ProjectSettings/ProjectVersion.txt").write_text('m_EditorVersion: 6000.3.12f1\n')
    return path


class ProjectCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = make_project(self.root / "Project")

    def parse(self, *arguments, cwd=None):
        with patch.object(sys, "argv", ["uagent", *arguments]), patch.object(Path, "cwd", return_value=cwd or self.project):
            return cli._parse_args()

    def test_explicit_and_legacy_paths_use_canonical_identity(self):
        for flag in ("--project-p", "--project-path"):
            with self.subTest(flag=flag):
                args = self.parse("doctor", flag, str(self.project / "Assets/.."))
                self.assertEqual(args.project_path, project_identity.canonicalize_project_root(self.project))

    def test_cwd_root_child_and_nearest_nested_project(self):
        nested = make_project(self.project / "Assets/Nested")
        for cwd, expected in ((self.project, self.project), (self.project / "Assets", self.project),
                              (nested, nested), (nested / "Assets", nested)):
            with self.subTest(cwd=cwd):
                self.assertEqual(self.parse("doctor", cwd=cwd).project_path,
                                 project_identity.canonicalize_project_root(expected))

    def test_relative_path_and_symlink(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            self.assertEqual(self.parse("doctor", "--project-p", "Project").project_path,
                             project_identity.canonicalize_project_root(self.project))
        finally:
            os.chdir(previous)
        link = self.root / "Linked"
        try:
            link.symlink_to(self.project, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks unavailable")
        self.assertEqual(self.parse("doctor", "--project-p", str(link)).project_path,
                         project_identity.canonicalize_project_root(self.project))

    def test_invalid_explicit_path_does_not_fall_back_to_cwd_or_parent(self):
        for path in ("", str(self.root / "Missing"), str(self.project / "Assets")):
            with self.subTest(path=path), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                self.parse("doctor", "--project-p", path)
            self.assertEqual(raised.exception.code, 2)

    def test_absent_project_does_not_search_children_and_explains_flag(self):
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit):
            self.parse("doctor", cwd=self.root)
        self.assertIn("--project-p", output.getvalue())

    def test_missing_manifest_or_version_is_not_a_project(self):
        for marker in ("Packages/manifest.json", "ProjectSettings/ProjectVersion.txt"):
            path = self.project / marker
            content = path.read_text()
            path.unlink()
            try:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    self.parse("doctor", "--project-p", str(self.project))
            finally:
                path.write_text(content)

    def test_project_flags_conflict_even_for_same_path(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse("doctor", "--project-p", str(self.project), "--project-path", str(self.project))

    def test_setup_positional_legacy_default_and_conflicting_operations(self):
        for arguments, expected in (([], "plan"), (["plan"], "plan"), (["apply"], "apply"),
                                    (["--operation", "doctor"], "doctor"),
                                    (["--operation", "apply"], "apply")):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.parse("setup", *arguments).operation, expected)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse("setup", "apply", "--operation", "plan")

    def test_all_project_commands_resolve_and_run_preserves_request_binding(self):
        for command in ("doctor", "setup", "e2e", "rock", "rock-import", "hot-reload"):
            arguments = [command] + (["plan"] if command not in {"doctor", "setup"} else [])
            with self.subTest(command=command):
                self.assertEqual(self.parse(*arguments).project_path,
                                 project_identity.canonicalize_project_root(self.project))
        args = self.parse("run", "--request", "request.json", cwd=self.root)
        self.assertFalse(hasattr(args, "project_path"))

    def test_cli_rejects_different_plan_project_before_approval_or_mutation(self):
        other = make_project(self.root / "Other")
        state = self.root / "state"
        cases = (("hot-reload", "hot-reload-plans", ("approve", "apply")),
                 ("rock", "rock-plans", ("approve", "apply")),
                 ("rock-import", "rock-import/plans", ("approve", "apply", "rollback")))
        for command, directory, operations in cases:
            plan_path = state / directory / "reviewed.json"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(json.dumps({"project_root": str(self.project)}))
            for operation in operations:
                with self.subTest(command=command, operation=operation):
                    output = io.StringIO()
                    with patch.object(sys, "argv", ["uagent", command, operation, "--project-p", str(other),
                                                   "--state-root", str(state), "--plan-id", "reviewed"]), redirect_stdout(output):
                        self.assertEqual(cli.main(), 1)
                    result = json.loads(output.getvalue())
                    self.assertEqual(result["status"], "blocked")
                    self.assertIn("Project", result["reason"])
        self.assertFalse((state / "approvals").exists())

    def test_setup_apply_rejects_plan_from_another_project_before_installer(self):
        plan_path = self.root / "approved.json"
        other = make_project(self.root / "Other")
        for payload in ({"project_root": str(self.project), "plan_id": "reviewed"},
                        {"outcome": {"provider_result": {"project_root": str(self.project), "plan_id": "reviewed"}}}):
            plan_path.write_text(json.dumps(payload))
            with patch.object(sys, "argv", ["uagent", "setup", "apply", "--project-p", str(other),
                                           "--approved-plan", str(plan_path), "--expected-plan-id", "reviewed",
                                           "--approval-ref", "approved", "--state-root", str(self.root / "state")]), \
                    patch.object(cli, "InstallerProvider") as installer, self.assertRaises(SystemExit) as raised:
                cli.main()
            self.assertIn("Project", str(raised.exception))
            installer.assert_not_called()

    def test_e2e_plan_cannot_be_applied_after_cwd_changes_project(self):
        state = self.root / "state"
        output = io.StringIO()
        with patch.object(sys, "argv", ["uagent", "e2e", "plan", "--state-root", str(state)]), \
                patch.object(Path, "cwd", return_value=self.project), redirect_stdout(output):
            self.assertEqual(cli.main(), 0)
        plan = json.loads(output.getvalue())
        other = make_project(self.root / "Other")
        for operation in ("approve", "approve-save", "apply"):
            output = io.StringIO()
            with patch.object(sys, "argv", ["uagent", "e2e", operation, "--state-root", str(state),
                                           "--plan-id", plan["plan_id"]]), \
                    patch.object(Path, "cwd", return_value=other), redirect_stdout(output):
                self.assertEqual(cli.main(), 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "blocked")
        self.assertEqual(list((other / "Assets").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
