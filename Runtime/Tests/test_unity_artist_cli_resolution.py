from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.Providers.UnityArtistCli.result_mapper import normalize_artist_result
from Runtime.Tooling.capability_resolver import ResolutionContext, resolve_capability


class UnityArtistCliResolutionTests(unittest.TestCase):
    """Resolver and evidence tests that do not depend on the host temp ACL."""

    def setUp(self) -> None:
        self.project_root = str(ROOT.resolve())
        self.snapshot = {
            "schema_version": "1.0",
            "project": {
                "root": self.project_root,
                "exists": True,
                "identity_status": "bound",
                "unity_version": "6000.6.0f1",
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
            "unity_cli": {
                "available": True,
                "version": "1.0.0-beta.8",
                "executable_path": "C:/Unity/unity.exe",
                "failure_class": None,
            },
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
            "myunitymcp": {
                "reachable": True,
                "available": True,
                "project_bound": True,
                "binding_status": "bound",
                "bound_instance_id": "mcp-1",
            },
            "coplay_mcp": {
                "reachable": False,
                "available": False,
                "project_bound": False,
                "binding_status": "unbound",
                "bound_instance_id": None,
            },
            "test_framework": {"available": True},
            "build": {
                "requested_target": None,
                "requested_target_module_available": "unknown",
            },
            "player_runtime": {"reachable": False, "instance_id": None},
            "profile_hint": "FULL",
            "binding_fingerprint": "0" * 64,
        }

    def test_semantic_artist_request_selects_artist_provider(self) -> None:
        request = {
            "schema_version": "1.0",
            "capability": "domain.workflow",
            "project_root": self.project_root,
            "operation_kind": "editor_mutation",
            "required_evidence": ["domain_result", "mutation_evidence"],
            "mutation_scope": {
                "allowed_paths": ["Assets/Scenes"],
                "prohibited_paths": ["ProjectSettings"],
            },
            "approval_ref": "approval-1",
            "preferred_surface": "editor",
            "qualifiers": {"domain": "visual_art", "workflow": "lighting"},
        }

        result = resolve_capability(
            request,
            self.snapshot,
            context=ResolutionContext(policy_allowed=True, approval_complete=True),
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["provider_ref"], "unity_artist_cli")

    def test_legacy_myunitymcp_is_not_selected_for_unqualified_scene_work(self) -> None:
        request = {
            "schema_version": "1.0",
            "capability": "scene.inspect",
            "project_root": self.project_root,
            "operation_kind": "read",
            "required_evidence": ["editor_observation"],
            "mutation_scope": None,
            "approval_ref": None,
            "preferred_surface": "editor",
        }

        snapshot = dict(self.snapshot)
        snapshot["unity_artist_cli"] = None
        snapshot["unity_cli"] = {
            "available": False,
            "version": None,
            "executable_path": None,
            "failure_class": "unavailable",
        }
        snapshot["unity_editor"] = dict(snapshot["unity_editor"])
        snapshot["unity_editor"]["installed"] = False
        snapshot["unity_editor"]["project_bound"] = False
        snapshot["unity_editor"]["running"] = False

        result = resolve_capability(
            request,
            snapshot,
            context=ResolutionContext(policy_allowed=True),
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["provider_ref"])
        self.assertIn("production-disabled", result["reason"])

    def test_nested_artist_evidence_is_preserved_as_semantic_tokens(self) -> None:
        result = normalize_artist_result(
            {
                "status": "passed",
                "data": {
                    "evidence": [
                        "visual_capture",
                        "camera_binding:MainCamera",
                        "capture_manifest",
                        "depth_channel:not_configured",
                    ]
                },
            },
            command="capture",
        )

        self.assertEqual(
            result["evidence"],
            ["visual_capture", "camera_binding", "capture_manifest"],
        )

    def test_host_adapter_nested_editor_result_is_mapped_to_evidence_and_provenance(self) -> None:
        editor_result = {
            "status": "passed",
            "planId": "artist-plan-live",
            "expectedRevision": "revision-live",
            "evidence": ["mutation_evidence", "undo_registration", "save_not_performed"],
        }
        result = normalize_artist_result(
            {
                "status": "passed",
                "data": {
                    "adapter": {"pipelineCommand": "artist.apply"},
                    "provider": {"data": {"result": json.dumps(editor_result)}},
                },
            },
            command="apply",
        )

        self.assertIn("mutation_evidence", result["evidence"])
        self.assertIn("undo_registration", result["evidence"])
        self.assertIn("save_not_performed", result["evidence"])
        self.assertEqual(result["redacted_provenance"]["plan_id"], "artist-plan-live")
        self.assertEqual(result["redacted_provenance"]["expected_revision"], "revision-live")


if __name__ == "__main__":
    unittest.main()
