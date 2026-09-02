from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Policy.Security.capability_policy import policy_for_capability
from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.tool_broker import ToolBroker

MATRIX_PATH = ROOT / "Eval/Datasets/Behavior/production-tool-runtime-environment-matrix.yaml"


def _merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class ProductionToolRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
        cls.project_root = cls.matrix["project_root"]

    def snapshot(self, profile: str) -> dict:
        base = self.matrix["base"]
        facts = {
            "schema_version": "1.0",
            "project": {
                "root": self.project_root,
                "exists": True,
                "identity_status": "bound",
                "unity_version": "6000.3.15f1",
                "required_paths": {"assets": True, "packages": True, "project_settings": True},
            },
            "filesystem": deepcopy(base["filesystem"]),
            "git": deepcopy(base["git"]),
            "unity_editor": {
                "installed": base["unity_editor"]["installed"],
                "version": "6000.3.15f1",
                "executable_path": "/opt/unity/Editor/Unity",
                "project_version_match": True,
                "running": base["unity_editor"]["running"],
                "safe_mode": base["unity_editor"]["safe_mode"],
                "project_bound": base["unity_editor"]["project_bound"],
                "binding_status": base["unity_editor"]["binding_status"],
                "bound_instance_id": None,
            },
            "unity_cli": {
                "available": base["unity_cli"]["available"],
                "version": "1.0.0-beta.3",
                "executable_path": "/usr/bin/unity",
                "failure_class": None,
            },
            "pipeline": deepcopy(base["pipeline"]),
            "myunitymcp": deepcopy(base["myunitymcp"]),
            "coplay_mcp": deepcopy(base["coplay_mcp"]),
            "test_framework": deepcopy(base["test_framework"]),
            "build": deepcopy(base["build"]),
            "player_runtime": deepcopy(base["player_runtime"]),
            "profile_hint": profile,
            "binding_fingerprint": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
        }
        facts = _merge(facts, self.matrix["profiles"][profile].get("overrides") or {})
        editor = facts["unity_editor"]
        if editor["installed"] is not True:
            editor["version"] = None
            editor["executable_path"] = None
            editor["project_version_match"] = False
            editor["project_bound"] = False
            editor["bound_instance_id"] = None
            if editor["running"] is not True:
                editor["binding_status"] = "not_running"
        if editor["binding_status"] == "bound":
            editor["bound_instance_id"] = "editor-1"
        cli = facts["unity_cli"]
        if cli["available"] is not True:
            cli["version"] = None
            cli["executable_path"] = None
            cli["failure_class"] = "unavailable"
        return facts

    def request(self, capability: str) -> dict:
        policy = policy_for_capability(capability)
        mutation = bool(policy["requires_mutation_scope"])
        approval = policy["approval_requirement"] in {
            "required_for_project_asset_or_settings_change",
            "always_required",
        }
        value = {
            "schema_version": "1.0",
            "capability": capability,
            "project_root": self.project_root,
            "operation_kind": policy["operation_kind"],
            "required_evidence": list(policy["minimum_required_evidence"]),
            "mutation_scope": (
                {"allowed_paths": ["Assets"], "prohibited_paths": ["ProjectSettings"]}
                if mutation
                else None
            ),
            "approval_ref": "approval-1" if approval else None,
            "preferred_surface": None,
        }
        validate_capability_request(value)
        return value

    def context(self, capability: str) -> ResolutionContext:
        policy = policy_for_capability(capability)
        approval = policy["approval_requirement"] in {
            "required_for_project_asset_or_settings_change",
            "always_required",
        }
        return ResolutionContext(
            policy_allowed=True,
            approval_required=approval,
            approval_complete=True if approval else False,
        )

    def test_environment_matrix_all_profiles(self):
        broker = ToolBroker()
        expected_profiles = {
            "FULL", "CLI_ONLY", "MCP_ONLY", "NATIVE_EDITOR", "FILES_ONLY",
            "SAFE_MODE", "NO_EDITOR", "PLAYER_UNAVAILABLE",
        }
        self.assertEqual(set(self.matrix["profiles"]), expected_profiles)
        for profile, fixture in self.matrix["profiles"].items():
            snapshot = self.snapshot(profile)
            for capability, expected in fixture["expectations"].items():
                resolution = broker.resolve(
                    self.request(capability),
                    snapshot,
                    context=self.context(capability),
                )
                self.assertEqual(
                    resolution["status"], expected["status"],
                    f"{profile}:{capability}:{resolution}",
                )
                self.assertEqual(
                    resolution.get("provider_ref"), expected.get("provider_ref"),
                    f"{profile}:{capability}:{resolution}",
                )

    def test_dynamic_provider_remove_and_add_changes_resolution_only(self):
        broker = ToolBroker()
        request = self.request("project.inspect")
        full = self.snapshot("FULL")
        first = broker.resolve(request, full, context=self.context("project.inspect"))
        self.assertEqual(first["provider_ref"], "myunitymcp")
        removed = deepcopy(full)
        removed["myunitymcp"].update(
            {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None}
        )
        second = broker.resolve(request, removed, context=self.context("project.inspect"))
        self.assertEqual(second["provider_ref"], "file")
        third = broker.resolve(request, full, context=self.context("project.inspect"))
        self.assertEqual(third["provider_ref"], "myunitymcp")

    def test_all_external_providers_absent_static_flow_remains_available(self):
        broker = ToolBroker()
        snapshot = self.snapshot("FILES_ONLY")
        static_result = broker.resolve(
            self.request("source.read"), snapshot, context=self.context("source.read")
        )
        editor_result = broker.resolve(
            self.request("scene.inspect"), snapshot, context=self.context("scene.inspect")
        )
        self.assertEqual(static_result["provider_ref"], "file")
        self.assertEqual(editor_result["status"], "unavailable")

    def test_missing_primary_executor_falls_back_same_capability(self):
        broker = ToolBroker()
        snapshot = self.snapshot("FULL")

        def native_executor(request, context, arguments):
            return {
                "status": "passed",
                "failure_class": None,
                "provider_ref": "native_unity_editor",
                "evidence": ["test_execution"],
                "tests": {"passed": 1, "failed": 0},
            }

        outcome = broker.dispatch(
            self.request("project.test"),
            snapshot,
            context=self.context("project.test"),
            executors={"native_unity_editor": native_executor},
        )
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["provider_result"]["provider_ref"], "native_unity_editor")
        self.assertEqual(outcome["fallback_from"], "unity_cli")
        self.assertEqual([item["provider_ref"] for item in outcome["attempts"]], ["unity_cli", "native_unity_editor"])

    def test_no_silent_weaker_mutation_fallback(self):
        broker = ToolBroker()
        snapshot = self.snapshot("FULL")
        outcome = broker.dispatch(
            self.request("scene.mutate"),
            snapshot,
            context=self.context("scene.mutate"),
            executors={},
        )
        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(outcome["attempts"][0]["provider_ref"], "myunitymcp")
        self.assertEqual(outcome["provider_result"]["failure_class"], "backend_not_implemented")
        self.assertNotIn("file", [item["provider_ref"] for item in outcome["attempts"]])

    def test_safe_mode_is_revalidated_at_execution_boundary(self):
        broker = ToolBroker()
        snapshot = self.snapshot("SAFE_MODE")

        def cli_safe_mode_block(request, context, arguments):
            return {
                "status": "failed",
                "failure_class": "precondition_failed",
                "reason": "Unity CLI execution is blocked while the project is in Safe Mode",
                "provider_ref": "unity_cli",
                "evidence": [],
            }

        outcome = broker.dispatch(
            self.request("project.test"),
            snapshot,
            context=self.context("project.test"),
            executors={"unity_cli": cli_safe_mode_block},
        )
        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(outcome["provider_result"]["failure_class"], "precondition_failed")
        self.assertEqual(len(outcome["attempts"]), 1)

    def test_player_unavailable_is_not_agent_wide_failure(self):
        broker = ToolBroker()
        snapshot = self.snapshot("PLAYER_UNAVAILABLE")
        player = broker.resolve(
            self.request("player.observe"), snapshot, context=self.context("player.observe")
        )
        static = broker.resolve(
            self.request("source.read"), snapshot, context=self.context("source.read")
        )
        self.assertEqual(player["status"], "unavailable")
        self.assertEqual(static["status"], "resolved")

    def test_executor_cannot_change_selected_provider_identity(self):
        broker = ToolBroker()
        snapshot = self.snapshot("FILES_ONLY")

        def wrong_provider(request, context, arguments):
            return {
                "status": "passed",
                "failure_class": None,
                "provider_ref": "unity_cli",
                "evidence": ["source_read"],
            }

        outcome = broker.dispatch(
            self.request("source.read"),
            snapshot,
            context=self.context("source.read"),
            executors={"file": wrong_provider},
        )
        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(outcome["provider_result"]["failure_class"], "ambiguous_binding")


if __name__ == "__main__":
    unittest.main()
