from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Policy.Security.capability_policy import policy_for_capability
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.fallback_policy import (
    FallbackPolicy,
    compose_partial_completion,
)


class FallbackPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project_root = str((Path(self.tmp.name) / "Project").resolve())
        project = Path(self.project_root)
        (project / "Assets/Scripts").mkdir(parents=True)
        (project / "Packages").mkdir()
        (project / "ProjectSettings").mkdir()

    def snapshot(
        self,
        *,
        cli: bool = True,
        editor: bool = True,
        myunity: bool = True,
        coplay: bool = True,
        player: bool = False,
    ) -> dict:
        return {
            "schema_version": "1.0",
            "project": {
                "root": self.project_root,
                "exists": True,
                "identity_status": "bound",
                "unity_version": "6000.3.12f1",
                "required_paths": {
                    "assets": True,
                    "packages": True,
                    "project_settings": True,
                },
            },
            "filesystem": {
                "readable": True,
                "writable": True,
                "writable_in_mutation_scope": True,
            },
            "git": {"available": True, "repository_bound": True},
            "unity_editor": {
                "installed": editor,
                "version": "6000.3.12f1" if editor else None,
                "executable_path": "/Unity" if editor else None,
                "project_version_match": True if editor else "unknown",
                "running": False,
                "safe_mode": False if editor else "unknown",
                "project_bound": False,
                "binding_status": "not_running",
                "bound_instance_id": None,
            },
            "unity_cli": {
                "available": cli,
                "version": "1.0" if cli else None,
                "executable_path": "/unity-cli" if cli else None,
                "failure_class": None if cli else "unavailable",
            },
            "pipeline": {"installed": cli, "reachable": cli},
            "myunitymcp": {
                "reachable": myunity,
                "available": myunity,
                "project_bound": myunity,
                "binding_status": "bound" if myunity else "unbound",
                "bound_instance_id": "mcp-1" if myunity else None,
            },
            "coplay_mcp": {
                "reachable": coplay,
                "available": coplay,
                "project_bound": coplay,
                "binding_status": "bound" if coplay else "unbound",
                "bound_instance_id": "coplay-1" if coplay else None,
            },
            "test_framework": {"available": True},
            "build": {
                "requested_target": "StandaloneWindows64",
                "requested_target_module_available": True,
            },
            "player_runtime": {
                "reachable": player,
                "instance_id": "player-1" if player else None,
            },
            "profile_hint": None,
            "binding_fingerprint": "0" * 64,
        }

    def request(
        self,
        capability: str,
        *,
        approval_ref: str | None = None,
        allowed_paths: list[str] | None = None,
    ) -> dict:
        policy = policy_for_capability(capability)
        scope = None
        if policy["requires_mutation_scope"]:
            scope = {
                "allowed_paths": allowed_paths or ["Assets/Scripts/Broken.cs"],
                "prohibited_paths": ["ProjectSettings"],
            }
        return {
            "schema_version": "1.0",
            "capability": capability,
            "project_root": self.project_root,
            "operation_kind": policy["operation_kind"],
            "required_evidence": list(policy["minimum_required_evidence"]),
            "mutation_scope": scope,
            "approval_ref": approval_ref,
            "preferred_surface": None,
        }

    def test_myunitymcp_unavailable_never_falls_back_to_raw_scene_file(self) -> None:
        request = self.request("scene.mutate", approval_ref="approval:scene")
        policy = FallbackPolicy()
        result = policy.after_failure(
            request,
            self.snapshot(cli=False, editor=False, myunity=False, coplay=False),
            context=ResolutionContext(policy_allowed=True, approval_complete=True),
            previous_provider_id="myunitymcp",
            provider_result={"status": "failed", "failure_class": "unavailable"},
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["provider_ref"])
        self.assertEqual(result["action"], "stop")

    def test_cli_unavailable_reresolves_project_test_to_native_editor(self) -> None:
        request = self.request("project.test")
        policy = FallbackPolicy()
        result = policy.after_failure(
            request,
            self.snapshot(cli=False, editor=True, myunity=False, coplay=False),
            context=ResolutionContext(policy_allowed=True),
            previous_provider_id="unity_cli",
            provider_result={"status": "failed", "failure_class": "unavailable"},
        )
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["action"], "fallback")
        self.assertEqual(result["provider_ref"], "native_unity_editor")
        self.assertEqual(result["fallback_from_provider_ref"], "unity_cli")

    def test_native_unavailable_can_preserve_static_work_as_partial_not_verified(self) -> None:
        result = compose_partial_completion(
            completed_results=[
                {"status": "passed", "evidence": ["source_read"]},
                {"status": "passed", "evidence": ["static_review"]},
            ],
            unresolved_capability="project.test",
            unresolved_result={
                "status": "unavailable",
                "failure_class": "unavailable",
            },
        )
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["verified"])
        self.assertEqual(result["completed_count"], 2)
        self.assertEqual(result["unresolved_capability"], "project.test")
        self.assertNotIn("test_execution", result["evidence"])

    def test_weaker_safety_or_evidence_fallback_is_rejected(self) -> None:
        request = self.request("scene.inspect")
        policy = FallbackPolicy()
        result = policy.after_failure(
            request,
            self.snapshot(cli=False, editor=False, myunity=False, coplay=True),
            context=ResolutionContext(policy_allowed=True),
            previous_provider_id="myunitymcp",
            provider_result={"status": "failed", "failure_class": "unavailable"},
        )
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["provider_ref"])
        self.assertEqual(result["action"], "stop")

    def test_scope_expansion_between_attempts_is_blocked_before_resolution(self) -> None:
        original = self.request("source.patch", allowed_paths=["Assets/Scripts/Broken.cs"])
        expanded = self.request("source.patch", allowed_paths=["Assets"])
        policy = FallbackPolicy()
        result = policy.after_failure(
            expanded,
            self.snapshot(cli=False, editor=False, myunity=False, coplay=False),
            context=ResolutionContext(policy_allowed=True),
            previous_provider_id="file",
            provider_result={"status": "failed", "failure_class": "unavailable"},
            original_request=original,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failure_class"], "scope_violation")
        self.assertEqual(result["action"], "stop")

    def test_timeout_retry_is_bounded_then_reresolves_same_capability(self) -> None:
        request = self.request("project.test")
        policy = FallbackPolicy(maximum_retry_attempts=1)
        snapshot = self.snapshot(cli=False, editor=True, myunity=False, coplay=False)
        first = policy.after_failure(
            request,
            snapshot,
            context=ResolutionContext(policy_allowed=True),
            previous_provider_id="unity_cli",
            provider_result={"status": "failed", "failure_class": "timeout"},
        )
        self.assertEqual(first["status"], "retry")
        self.assertEqual(first["provider_ref"], "unity_cli")
        second = policy.after_failure(
            request,
            snapshot,
            context=ResolutionContext(policy_allowed=True),
            previous_provider_id="unity_cli",
            provider_result={"status": "failed", "failure_class": "timeout"},
        )
        self.assertEqual(second["status"], "resolved")
        self.assertEqual(second["provider_ref"], "native_unity_editor")
        self.assertEqual(second["action"], "fallback")

    def test_observed_test_failure_is_terminal_not_provider_fallback(self) -> None:
        request = self.request("project.test")
        policy = FallbackPolicy()
        result = policy.after_failure(
            request,
            self.snapshot(),
            context=ResolutionContext(policy_allowed=True),
            previous_provider_id="unity_cli",
            provider_result={
                "status": "failed",
                "failure_class": "observed_test_failure",
                "evidence": ["test_execution"],
            },
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failure_class"], "observed_test_failure")
        self.assertEqual(result["action"], "stop")

    def test_not_observed_is_partial_and_never_promoted_to_pass(self) -> None:
        request = self.request("project.test")
        policy = FallbackPolicy()
        result = policy.after_failure(
            request,
            self.snapshot(),
            context=ResolutionContext(policy_allowed=True),
            previous_provider_id="unity_cli",
            provider_result={"status": "failed", "failure_class": "not_observed"},
        )
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["verified"])
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["action"], "partial")


if __name__ == "__main__":
    unittest.main()
