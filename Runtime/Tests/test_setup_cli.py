from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from Tools import unity_agent_cli
from Runtime.Tooling.Providers.Installer.codex_plugin_installer import CommandResult


class SetupCliTests(unittest.TestCase):
    def test_doctor_exit_code_is_zero_when_optional_artist_cli_is_unavailable(self) -> None:
        real_installer_type = unity_agent_cli.InstallerProvider
        with tempfile.TemporaryDirectory(prefix="unity-agent-doctor-") as temp_root:
            root = Path(temp_root)
            project_root = root / "Project"
            project_root.mkdir()
            fake_codex = root / "codex.exe"
            fake_codex.write_text("test executable", encoding="utf-8")
            stdout = io.StringIO()

            def command_runner(arguments):
                if arguments[1:] == ["--version"]:
                    return CommandResult(0, "codex-cli 0.0-test\n", "")
                if arguments[1:] == ["plugin", "list", "--json"]:
                    return CommandResult(0, '[{"pluginId":"unity-agent@unity-agent","version":"0.0.7-beta","installed":true,"enabled":true}]', "")
                raise AssertionError(f"unexpected command: {arguments}")

            def installer_factory(project_path):
                return real_installer_type(
                    project_path,
                    which_fn=lambda name: "/usr/bin/unity" if name == "unity" else (str(fake_codex) if name == "codex" else None),
                    command_runner=command_runner,
                    env={},
                )

            args = [
                "unity-agent",
                "setup",
                "--operation", "doctor",
                "--project-path", str(project_root),
                "--product", "unity_artist_cli",
                "--product", "official_unity_cli",
                "--product", "codex_cli",
                "--product", "unity_agent_codex_plugin",
                "--codex-path", str(fake_codex),
                "--state-root", str(root / "state"),
                "--format", "json",
                "--non-interactive",
            ]
            with patch.object(sys, "argv", args), patch.object(
                unity_agent_cli, "InstallerProvider", installer_factory
            ), redirect_stdout(stdout):
                exit_code = unity_agent_cli.main()

        result = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "completed")
        provider_result = result["outcome"]["provider_result"]
        self.assertEqual(provider_result["status"], "passed")
        entries_by_product = {entry["product"]: entry for entry in provider_result["entries"]}
        self.assertEqual(entries_by_product["unity_artist_cli"]["status"], "unavailable")
        self.assertEqual(
            entries_by_product["unity_artist_cli"]["reason"],
            "unity_artist_cli_unavailable",
        )
        self.assertEqual(entries_by_product["official_unity_cli"]["status"], "verified")
        self.assertEqual(entries_by_product["codex_cli"]["status"], "verified")
        self.assertEqual(entries_by_product["unity_agent_codex_plugin"]["status"], "verified")


if __name__ == "__main__":
    unittest.main()
