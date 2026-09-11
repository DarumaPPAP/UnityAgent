from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.Providers.UnityArtistCli.unity_artist_cli_provider import UnityArtistCliProvider


class FakeArtistDispatch:
    def __init__(self, payload: dict):
        self.payload = payload
        self.requests = []

    def __call__(self, request, *, cancel_event=None):
        self.requests.append(request)
        return {"status": "passed", "failure_class": None, "payload": self.payload}


class UnityArtistCliProviderTests(unittest.TestCase):
    def setUp(self):
        self.project_root = str(ROOT.resolve())
        self.snapshot = {
            "schema_version": "1.0",
            "project": {
                "root": self.project_root,
                "exists": True,
                "identity_status": "bound",
                "unity_version": "6000.6.0f1",
                "required_paths": {"assets": True, "packages": True, "project_settings": True},
            },
            "filesystem": {"readable": True, "writable": True, "writable_in_mutation_scope": True},
            "git": {"available": True, "repository_bound": True},
            "unity_editor": {
                "installed": True,
                "version": "6000.6.0f1",
                "executable_path": "C:/Unity/Editor.exe",
                "project_version_match": True,
                "running": True,
                "safe_mode": False,
                "project_bound": True,
                "binding_status": "bound",
                "bound_instance_id": "editor-1",
            },
            "unity_cli": {"available": True, "version": "1.0.0-beta.8", "executable_path": "C:/Unity/unity.exe", "failure_class": None},
            "unity_artist_cli": {
                "available": True,
                "version": "2.0.0",
                "executable_path": "C:/Tools/unity-artist.exe",
                "project_bound": True,
                "package_installed": True,
                "package_version": "2.0.0",
                "pipeline_reachable": True,
                "unity_version": "6000.6.0f1",
                "render_pipeline": "builtin",
                "support_tier": "primary",
                "compatibility_backend": "builtin_editor_api",
                "capabilities": ["visual_art.lookdev_plan", "cinematic.timeline_plan"],
                "failure_class": None,
                "binding_status": "bound",
                "bound_instance_id": "unity-artist:project",
            },
            "pipeline": {"installed": True, "reachable": True},
            "myunitymcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
            "coplay_mcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
            "test_framework": {"available": True},
            "build": {"requested_target": None, "requested_target_module_available": "unknown"},
            "player_runtime": {"reachable": False, "instance_id": None},
            "profile_hint": "FULL",
            "binding_fingerprint": "0" * 64,
        }
        self.request = {
            "schema_version": "1.0",
            "capability": "domain.workflow",
            "project_root": self.project_root,
            "operation_kind": "editor_mutation",
            "required_evidence": ["domain_result", "mutation_evidence"],
            "mutation_scope": {"allowed_paths": ["Assets"], "prohibited_paths": ["ProjectSettings"]},
            "approval_ref": "approval-1",
            "preferred_surface": "editor",
            "qualifiers": {"domain": "visual_art", "workflow": "lighting"},
        }

    def test_allowlisted_command_uses_existing_dispatcher_and_structured_result(self):
        fake = FakeArtistDispatch({"Status": "passed", "Data": {"planId": "plan-1", "diffDigest": "sha256:diff"}})
        provider = UnityArtistCliProvider(self.project_root, self.snapshot, dispatch_fn=fake)

        result = provider.execute(self.request, arguments={"command": "plan", "workflow": "lighting"})

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["provider_ref"], "unity_artist_cli")
        self.assertEqual(result["evidence"], ["domain_result"])
        self.assertEqual(len(fake.requests), 1)
        self.assertIn("plan", fake.requests[0].command)
        self.assertNotIn("eval", " ".join(fake.requests[0].command).casefold())

    def test_apply_emits_redacted_mutation_provenance(self):
        fake = FakeArtistDispatch({"Status": "passed", "Data": {"planId": "plan-1", "sessionId": "session-1", "expectedRevision": 4, "diffDigest": "sha256:diff"}})
        provider = UnityArtistCliProvider(self.project_root, self.snapshot, dispatch_fn=fake)

        result = provider.execute(
            self.request,
            arguments={"command": "apply", "approval_token": "opaque-token", "expected_revision": 4},
        )

        self.assertEqual(result["evidence"], ["domain_result", "mutation_evidence"])
        self.assertNotIn("opaque-token", str(result))
        self.assertEqual(result["redacted_provenance"]["plan_id"], "plan-1")

    def test_unknown_command_is_rejected_before_dispatch(self):
        fake = FakeArtistDispatch({"Status": "passed", "Data": {}})
        provider = UnityArtistCliProvider(self.project_root, self.snapshot, dispatch_fn=fake)

        result = provider.execute(self.request, arguments={"command": "eval"})

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_class"], "precondition_failed")
        self.assertEqual(fake.requests, [])


if __name__ == "__main__":
    unittest.main()
