from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.Providers.Installer.codex_plugin_installer import (
    CodexPluginInstallError,
    CommandResult,
    ensure_codex_plugin,
    observe_codex_plugin,
)
from Runtime.Tooling.Providers.Installer.installer_provider import InstallerProvider
from Runtime.Tooling.Providers.Installer.release_installer import ReleaseInstallError, install_plan


class InstallerProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.install_root = ROOT / f".tmp-installer-{uuid.uuid4().hex}"
        self.addCleanup(lambda: shutil.rmtree(self.install_root, ignore_errors=True))

    @staticmethod
    def archive(*, unsafe: bool = False) -> bytes:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as package:
            package.writestr("payload/unity-artist.exe", b"UnityArtistCLI beta test payload")
            if unsafe:
                package.writestr("../escape.txt", b"must not extract")
        return stream.getvalue()

    def test_release_archive_is_hash_verified_and_installed_to_requested_root(self) -> None:
        archive = self.archive()
        digest = hashlib.sha256(archive).hexdigest()
        urls: list[str] = []

        def download(url: str) -> bytes:
            urls.append(url)
            return archive if url.endswith(".zip") else f"{digest}  archive.zip\n".encode("utf-8")

        result = install_plan(
            {
                "project_root": str(ROOT),
                "plan_id": "plan-test",
                "channel": "0.0.4-beta",
                "install_root": str(self.install_root),
                "actions": [{"product": "unity_artist_cli", "action": "install_then_verify"}],
            },
            download_fn=download,
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["channel"], "0.0.4-beta")
        self.assertEqual(result["entries"][0]["version"], "0.0.1-beta")
        self.assertTrue((self.install_root / "unity-artist.exe").is_file())
        self.assertEqual(result["install_receipt"]["entries"][0]["sha256"], f"sha256:{digest}")
        self.assertEqual(len(urls), 2)

    def test_archive_path_escape_is_rejected(self) -> None:
        archive = self.archive(unsafe=True)
        digest = hashlib.sha256(archive).hexdigest()

        def download(url: str) -> bytes:
            return archive if url.endswith(".zip") else f"{digest}\n".encode("utf-8")

        with self.assertRaises(ReleaseInstallError):
            install_plan(
                {
                    "project_root": str(ROOT),
                    "plan_id": "plan-unsafe",
                    "channel": "0.0.4-beta",
                    "install_root": str(self.install_root),
                    "actions": [{"product": "unity_artist_cli", "action": "install_then_verify"}],
                },
                download_fn=download,
            )

    def test_codex_plugin_observation_requires_codex_cli(self) -> None:
        result = observe_codex_plugin(None)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "codex_cli_unavailable")

    def test_codex_plugin_observation_reports_installed_plugin(self) -> None:
        def runner(arguments):
            return CommandResult(
                0,
                json.dumps([
                    {
                        "pluginId": "unity-agent@unity-agent",
                        "name": "unity-agent",
                        "marketplaceName": "unity-agent",
                        "version": "0.0.4-beta",
                        "installed": True,
                        "enabled": True,
                        "installedPath": "C:/Users/test/.codex/plugins/unity-agent",
                    }
                ]),
                "",
            )

        result = observe_codex_plugin("C:/Tools/codex.exe", runner=runner)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["version"], "0.0.4-beta")

    def test_codex_plugin_install_adds_pinned_marketplace_and_verifies(self) -> None:
        calls: list[list[str]] = []

        def runner(arguments):
            args = list(arguments)
            calls.append(args)
            if args[2:5] == ["list", "--available", "--json"]:
                return CommandResult(0, "[]", "")
            if args[2:5] == ["marketplace", "list", "--json"]:
                return CommandResult(0, "[]", "")
            if args[2:5] == ["marketplace", "add", "DarumaPPAP/UnityAgent"]:
                return CommandResult(0, json.dumps({"name": "unity-agent"}), "")
            if args[2:4] == ["add", "unity-agent@unity-agent"]:
                return CommandResult(0, json.dumps({"pluginId": "unity-agent@unity-agent"}), "")
            if args[2:4] == ["list", "--json"]:
                return CommandResult(
                    0,
                    json.dumps([
                        {
                            "pluginId": "unity-agent@unity-agent",
                            "name": "unity-agent",
                            "marketplaceName": "unity-agent",
                            "version": "0.0.4-beta",
                            "installed": True,
                            "enabled": True,
                            "installedPath": "C:/Users/test/.codex/plugins/unity-agent",
                        }
                    ]),
                    "",
                )
            return CommandResult(1, "", f"unexpected command: {args}")

        result = ensure_codex_plugin("C:/Tools/codex.exe", runner=runner)
        self.assertEqual(result["status"], "installed")
        self.assertIn(
            [
                "C:/Tools/codex.exe", "plugin", "marketplace", "add",
                "DarumaPPAP/UnityAgent", "--ref", "v0.0.4-beta", "--json",
            ],
            calls,
        )
        self.assertIn(
            ["C:/Tools/codex.exe", "plugin", "add", "unity-agent@unity-agent", "--json"],
            calls,
        )

    def test_codex_marketplace_collision_fails_closed(self) -> None:
        def runner(arguments):
            args = list(arguments)
            if args[2:5] == ["list", "--available", "--json"]:
                return CommandResult(0, "[]", "")
            if args[2:5] == ["marketplace", "list", "--json"]:
                return CommandResult(
                    0,
                    json.dumps([
                        {
                            "name": "unity-agent",
                            "source": {"url": "https://github.com/Other/PluginRepo", "ref": "main"},
                        }
                    ]),
                    "",
                )
            return CommandResult(1, "", "must not mutate a conflicting marketplace")

        with self.assertRaises(CodexPluginInstallError):
            ensure_codex_plugin("C:/Tools/codex.exe", runner=runner)

    def test_installer_plan_blocks_plugin_install_when_codex_is_missing(self) -> None:
        provider = InstallerProvider(ROOT, which_fn=lambda name: None, env={})
        plan = provider.plan({
            "project_root": str(ROOT),
            "products": ["unity_agent_codex_plugin"],
            "channel": "0.0.4-beta",
            "install_root": None,
            "codex_cli_path": None,
        })
        self.assertEqual(plan["status"], "unavailable")
        self.assertEqual(plan["actions"][0]["action"], "blocked_by_dependency")
        self.assertFalse(plan["approval_required"])

    def test_installer_honors_explicit_codex_cli_path(self) -> None:
        fake_codex = self.install_root / "codex.cmd"
        fake_codex.parent.mkdir(parents=True, exist_ok=True)
        fake_codex.write_text("@echo off\n", encoding="utf-8")
        provider = InstallerProvider(ROOT, which_fn=lambda name: None, env={})
        result = provider.doctor({
            "products": ["codex_cli"],
            "codex_cli_path": str(fake_codex),
        })
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["entries"][0]["location"], str(fake_codex.resolve()))
        self.assertEqual(result["entries"][0]["source"], "explicit_override")

    def test_installer_finds_codex_in_windows_npm_style_location(self) -> None:
        app_data = self.install_root / "AppData/Roaming"
        fake_codex = app_data / "npm/codex.cmd"
        fake_codex.parent.mkdir(parents=True, exist_ok=True)
        fake_codex.write_text("@echo off\n", encoding="utf-8")
        provider = InstallerProvider(
            ROOT,
            which_fn=lambda name: None,
            env={"APPDATA": str(app_data)},
        )
        result = provider.doctor({
            "products": ["codex_cli"],
            "codex_cli_path": None,
        })
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["entries"][0]["location"], str(fake_codex.resolve()))
        self.assertEqual(result["entries"][0]["source"], "well_known_windows_location")


if __name__ == "__main__":
    unittest.main()
