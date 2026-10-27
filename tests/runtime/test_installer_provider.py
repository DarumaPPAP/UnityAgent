from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from jsonschema import ValidationError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unityagent.runtime.tooling.providers.installer.codex_plugin_installer import (
    CodexPluginInstallError,
    CommandResult,
    ensure_codex_plugin,
    observe_codex_plugin,
)
from unityagent.runtime.tooling.providers.installer.installer_provider import InstallerProvider
from unityagent.runtime.tooling.providers.installer.release_installer import ReleaseInstallError, install_plan
from unityagent.runtime.contracts.toolchain_setup_contract import validate_toolchain_setup_request


class InstallerProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.install_root = ROOT / f".tmp-installer-{uuid.uuid4().hex}"
        self.addCleanup(lambda: shutil.rmtree(self.install_root, ignore_errors=True))

    @staticmethod
    def codex_version_runner(arguments):
        return CommandResult(0, "codex-cli 0.0-test\n", "")

    def test_removed_host_product_is_rejected_without_installation(self):
        with self.assertRaises(ReleaseInstallError):
            install_plan({"actions": [{"product": "unity_artist_cli", "action": "install_then_verify"}]})
        self.assertFalse(self.install_root.exists())

    def test_artist_package_doctor_never_searches_for_host_and_plan_is_manual(self):
        lookups = []
        provider = InstallerProvider(self.install_root, which_fn=lambda name: lookups.append(name), env={})
        missing = provider.plan({"products": ["artist_subagent"]})
        self.assertEqual(missing["status"], "unavailable")
        self.assertEqual(missing["actions"][0]["action"], "manual_required")
        self.assertFalse(missing["approval_required"])
        self.assertEqual(lookups, [])
        packages = self.install_root / "Packages"
        packages.mkdir(parents=True)
        (packages / "manifest.json").write_text(json.dumps({"dependencies": {"com.darumappap.artist-subagent": "file:../artist"}}), encoding="utf-8")
        observed = provider.doctor({"products": ["artist_subagent"]})
        self.assertEqual(observed["entries"][0]["status"], "verified")
        self.assertEqual(observed["entries"][0]["location"], str(packages / "manifest.json"))
        self.assertEqual(lookups, [])

    def test_release_adapter_verifies_official_cli_and_package_without_installing(self):
        actions = [{"product": product, "action": "verify", "location": "/observed/" + product, "version": "observed"} for product in ("official_unity_cli", "artist_subagent")]
        result = install_plan({"actions": actions})
        self.assertEqual(result["status"], "passed")
        self.assertEqual([entry["product"] for entry in result["entries"]], ["official_unity_cli", "artist_subagent"])
        with self.assertRaises(ReleaseInstallError):
            install_plan({"actions": [{"product": "artist_subagent", "action": "install_then_verify"}]})

    def test_current_setup_schema_accepts_package_and_rejects_removed_host(self):
        request = {"schema_version": "1.0", "request_id": "setup-package", "entry_point": "codex_plugin", "operation": "doctor", "project_root": str(ROOT), "products": ["artist_subagent"], "channel": "0.0.8-beta", "non_interactive": True}
        validate_toolchain_setup_request(request, root=ROOT)
        request["products"] = ["unity_artist_cli"]
        with self.assertRaises(ValidationError) as raised:
            validate_toolchain_setup_request(request, root=ROOT)
        self.assertIn("unity_artist_cli", str(raised.exception))

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
                        "version": "0.0.8-beta",
                        "installed": True,
                        "enabled": True,
                        "installedPath": "C:/CodexFixture/plugins/unity-agent",
                    }
                ]),
                "",
            )

        result = observe_codex_plugin("C:/Tools/codex.exe", runner=runner)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["version"], "0.0.8-beta")

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
                            "version": "0.0.8-beta",
                            "installed": True,
                            "enabled": True,
                            "installedPath": "C:/CodexFixture/plugins/unity-agent",
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
                "DarumaPPAP/UnityAgent", "--ref", "v0.0.8-beta", "--json",
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
            "channel": "0.0.8-beta",
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
        provider = InstallerProvider(
            ROOT,
            which_fn=lambda name: None,
            env={},
            command_runner=self.codex_version_runner,
        )
        result = provider.doctor({
            "products": ["codex_cli"],
            "codex_cli_path": str(fake_codex),
        })
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["entries"][0]["location"], str(fake_codex.resolve()))
        self.assertEqual(result["entries"][0]["source"], "explicit_override")
        self.assertEqual(result["entries"][0]["version"], "codex-cli 0.0-test")

    def test_installer_finds_codex_in_windows_npm_style_location(self) -> None:
        app_data = self.install_root / "AppData/Roaming"
        fake_codex = app_data / "npm/codex.cmd"
        fake_codex.parent.mkdir(parents=True, exist_ok=True)
        fake_codex.write_text("@echo off\n", encoding="utf-8")
        provider = InstallerProvider(
            ROOT,
            which_fn=lambda name: None,
            env={"APPDATA": str(app_data)},
            command_runner=self.codex_version_runner,
        )
        result = provider.doctor({
            "products": ["codex_cli"],
            "codex_cli_path": None,
        })
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["entries"][0]["location"], str(fake_codex.resolve()))
        self.assertEqual(result["entries"][0]["source"], "windows_npm")

    def test_installer_reports_codex_execution_failure_readably(self) -> None:
        fake_codex = self.install_root / "codex.cmd"
        fake_codex.parent.mkdir(parents=True, exist_ok=True)
        fake_codex.write_text("@echo off\n", encoding="utf-8")
        provider = InstallerProvider(
            ROOT,
            which_fn=lambda name: None,
            env={},
            command_runner=lambda arguments: CommandResult(7, "", "broken shim"),
        )
        result = provider.doctor({
            "products": ["codex_cli"],
            "codex_cli_path": str(fake_codex),
        })
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["entries"][0]["reason"], "codex_cli_execution_failed")
        self.assertIn("broken shim", result["entries"][0]["message"])

    def test_doctor_keeps_optional_artist_unavailable_without_blocking_other_products(self) -> None:
        project_root = self.install_root / "Project"
        project_root.mkdir(parents=True)
        fake_codex = self.install_root / "codex.exe"
        fake_codex.write_text("test executable", encoding="utf-8")

        def runner(arguments):
            if arguments[1:] == ["--version"]:
                return CommandResult(0, "codex-cli 0.0-test\n", "")
            if arguments[1:] == ["plugin", "list", "--json"]:
                return CommandResult(
                    0,
                    json.dumps([{
                        "pluginId": "unity-agent@unity-agent",
                        "name": "unity-agent",
                        "marketplaceName": "unity-agent",
                        "version": "0.0.8-beta",
                        "installed": True,
                        "enabled": True,
                        "installedPath": "C:/CodexFixture/plugins/unity-agent",
                    }]),
                    "",
                )
            raise AssertionError(f"unexpected command: {arguments}")

        provider = InstallerProvider(
            project_root,
            which_fn=lambda name: "/tools/unity.exe" if name == "unity" else None,
            command_runner=runner,
            env={},
        )
        result = provider.doctor({
            "products": [
                "official_unity_cli",
                "artist_subagent",
                "codex_cli",
                "unity_agent_codex_plugin",
            ],
            "codex_cli_path": str(fake_codex),
        })

        self.assertEqual(result["status"], "passed")
        entries = {entry["product"]: entry for entry in result["entries"]}
        self.assertEqual(entries["official_unity_cli"]["status"], "verified")
        self.assertEqual(entries["artist_subagent"]["status"], "unavailable")
        self.assertEqual(entries["artist_subagent"]["reason"], "artist_package_not_installed")
        self.assertEqual(entries["codex_cli"]["status"], "verified")
        self.assertEqual(entries["unity_agent_codex_plugin"]["status"], "verified")
        self.assertTrue(any("ArtistSubAgent" in item for item in result["errors"]))

    def test_doctor_keeps_product_execution_exception_distinct_from_unavailable(self) -> None:
        project_root = self.install_root / "Project"
        project_root.mkdir(parents=True)
        fake_codex = self.install_root / "codex.exe"
        fake_codex.write_text("test executable", encoding="utf-8")
        provider = InstallerProvider(
            project_root,
            which_fn=lambda name: None,
            command_runner=lambda arguments: (_ for _ in ()).throw(RuntimeError("simulated CLI failure")),
            env={},
        )

        result = provider.doctor({
            "products": ["codex_cli"],
            "codex_cli_path": str(fake_codex),
        })

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["entries"][0]["status"], "failed")
        self.assertEqual(result["entries"][0]["failure_class"], "execution_failed")
        self.assertIn("simulated CLI failure", result["entries"][0]["message"])

    def test_doctor_keeps_observed_plugin_version_mismatch_as_incompatible(self) -> None:
        project_root = self.install_root / "Project"
        project_root.mkdir(parents=True)
        fake_codex = self.install_root / "codex.exe"
        fake_codex.write_text("test executable", encoding="utf-8")

        def runner(arguments):
            if arguments[1:] == ["plugin", "list", "--json"]:
                return CommandResult(
                    0,
                    json.dumps([{
                        "pluginId": "unity-agent@unity-agent",
                        "version": "0.0.6-beta",
                        "installed": True,
                        "enabled": True,
                    }]),
                    "",
                )
            raise AssertionError(f"unexpected command: {arguments}")

        provider = InstallerProvider(
            project_root,
            command_runner=runner,
            env={},
        )
        result = provider.doctor({
            "products": ["unity_agent_codex_plugin"],
            "codex_cli_path": str(fake_codex),
        })

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["entries"][0]["status"], "stale")
        self.assertEqual(result["entries"][0]["reason"], "plugin_version_mismatch")

    def test_missing_artist_plan_requires_explicit_package_setup_and_does_not_install(self) -> None:
        project_root = self.install_root / "Project"
        project_root.mkdir(parents=True)
        install_calls = []
        provider = InstallerProvider(
            project_root,
            which_fn=lambda name: None,
            installer_fn=lambda plan: install_calls.append(plan) or {"status": "passed"},
            env={},
        )

        plan = provider.plan({
            "project_root": str(project_root),
            "products": ["artist_subagent"],
            "channel": "0.0.8-beta",
            "install_root": str(self.install_root / "install"),
        })

        self.assertEqual(plan["status"], "unavailable")
        self.assertEqual(plan["actions"][0]["action"], "manual_required")
        self.assertFalse(plan["approval_required"])
        self.assertEqual(install_calls, [])

    def test_codex_plugin_plan_is_independent_of_missing_artist_backend(self) -> None:
        project_root = self.install_root / "Project"
        project_root.mkdir(parents=True)
        fake_codex = self.install_root / "codex.exe"
        fake_codex.write_text("test executable", encoding="utf-8")
        install_calls = []
        observed_commands = []
        observed_lookups = []

        def which(name):
            observed_lookups.append(name)
            return str(fake_codex) if name == "codex" else None

        def runner(arguments):
            observed_commands.append(list(arguments))
            if arguments[1:] == ["--version"]:
                return CommandResult(0, "codex-cli 0.0-test\n", "")
            if arguments[1:] == ["plugin", "list", "--json"]:
                return CommandResult(0, '[{"pluginId":"unity-agent@unity-agent","version":"0.0.8-beta","installed":true,"enabled":true}]', "")
            raise AssertionError(f"unexpected command: {arguments}")

        provider = InstallerProvider(
            project_root,
            which_fn=which,
            command_runner=runner,
            installer_fn=lambda plan: install_calls.append(plan) or {"status": "passed"},
            env={},
        )
        artist_report = provider.doctor({"products": ["artist_subagent"]})
        self.assertEqual(artist_report["entries"][0]["status"], "unavailable")
        observed_lookups.clear()
        observed_commands.clear()

        plan = provider.plan({
            "project_root": str(project_root),
            "products": ["codex_cli", "unity_agent_codex_plugin"],
            "channel": "0.0.8-beta",
            "install_root": str(self.install_root / "install"),
            "codex_cli_path": str(fake_codex),
        })

        self.assertEqual(plan["status"], "passed")
        self.assertFalse(plan["approval_required"])
        self.assertEqual([action["action"] for action in plan["actions"]], ["verify", "verify"])
        self.assertNotIn("unity-artist", observed_lookups)
        self.assertEqual(len(observed_commands), 2)
        self.assertEqual(install_calls, [])

    def test_apply_without_completed_approval_stops_before_install(self) -> None:
        project_root = self.install_root / "Project"
        project_root.mkdir(parents=True)
        install_calls = []
        provider = InstallerProvider(
            project_root,
            installer_fn=lambda plan: install_calls.append(plan) or {"status": "passed"},
            env={},
        )

        result = provider.apply(
            {"approval_ref": "approval-1", "expected_plan_id": "plan-1"},
            approval_complete=False,
            approved_plan={"plan_id": "plan-1", "status": "passed"},
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_class"], "blocked_by_approval")
        self.assertEqual(install_calls, [])


if __name__ == "__main__":
    unittest.main()
