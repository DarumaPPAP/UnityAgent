from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.Providers.PlayerRuntime.player_runtime_provider import (
    PlayerBuildArtifact,
    PlayerRuntimeProvider,
    RuntimeEndpointObservation,
)
from Runtime.Tooling.capability_resolver import ResolutionContext


class FakeTransport:
    def __init__(self, endpoint: RuntimeEndpointObservation, *, result: dict | None = None):
        self.endpoints = [endpoint]
        self.result = result
        self.invocations = []
        self.raise_on_invoke = None

    def discover(self):
        return list(self.endpoints)

    def invoke(self, *, instance_id, command_id, arguments, timeout_seconds):
        self.invocations.append((instance_id, command_id, dict(arguments), timeout_seconds))
        if self.raise_on_invoke is not None:
            raise self.raise_on_invoke
        if self.result is not None:
            return dict(self.result)
        endpoint = self.endpoints[0]
        return {
            "status": "passed",
            "instance_id": endpoint.instance_id,
            "command_id": command_id,
            "project_root": endpoint.project_root,
            "artifact_id": endpoint.artifact_id,
            "session_revision": endpoint.session_revision,
            "payload": {"value": 1},
        }


class PlayerRuntimeProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project_root = str((Path(self.tmp.name) / "Project").resolve())
        project = Path(self.project_root)
        (project / "Assets").mkdir(parents=True)
        (project / "Packages").mkdir()
        (project / "ProjectSettings").mkdir()
        self.endpoint = RuntimeEndpointObservation(
            instance_id="player-1",
            reachable=True,
            project_root=self.project_root,
            artifact_id="artifact-1",
            build_kind="development",
            catalog_revision="1.0",
            session_revision="session-1",
            target_device_id="switch-devkit-1",
        )
        self.transport = FakeTransport(self.endpoint)

    def snapshot(self, *, reachable=True, instance_id="player-1"):
        return {
            "schema_version": "1.0",
            "project": {
                "root": self.project_root,
                "exists": True,
                "identity_status": "bound",
                "unity_version": "6000.3.15f1",
                "required_paths": {"assets": True, "packages": True, "project_settings": True},
            },
            "filesystem": {"readable": True, "writable": True, "writable_in_mutation_scope": True},
            "git": {"available": True, "repository_bound": True},
            "unity_editor": {
                "installed": True,
                "version": "6000.3.15f1",
                "executable_path": "/Unity",
                "project_version_match": True,
                "running": False,
                "safe_mode": False,
                "project_bound": False,
                "binding_status": "not_running",
                "bound_instance_id": None,
            },
            "unity_cli": {"available": False, "version": None, "executable_path": None, "failure_class": "unavailable"},
            "pipeline": {"installed": False, "reachable": False},
            "myunitymcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
            "coplay_mcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
            "test_framework": {"available": True},
            "build": {"requested_target": None, "requested_target_module_available": "unknown"},
            "player_runtime": {"reachable": reachable, "instance_id": instance_id},
            "profile_hint": "FULL",
            "binding_fingerprint": "0" * 64,
        }

    def artifact(self, *, build_kind="development", enabled=True, revision="1.0"):
        return PlayerBuildArtifact(
            artifact_id="artifact-1",
            project_root=self.project_root,
            build_kind=build_kind,
            command_surface_enabled=enabled,
            catalog_revision=revision,
        )

    def provider(self, *, artifact=None, snapshot=None, transport=None):
        return PlayerRuntimeProvider(
            self.project_root,
            snapshot or self.snapshot(),
            build_artifact=artifact or self.artifact(),
            transport=transport or self.transport,
        )

    def request(self, capability="player.observe", *, approval=False):
        mutate = capability == "player.mutate"
        return {
            "schema_version": "1.0",
            "capability": capability,
            "project_root": self.project_root,
            "operation_kind": "player_mutate" if mutate else "player_observe",
            "required_evidence": ["player_observation", "mutation_evidence"] if mutate else ["player_observation"],
            "mutation_scope": {"allowed_paths": ["Assets"], "prohibited_paths": ["ProjectSettings"]} if mutate else None,
            "approval_ref": "approval-1" if approval else None,
            "preferred_surface": "player",
        }

    def test_release_build_hides_entire_command_surface(self):
        provider = self.provider(artifact=self.artifact(build_kind="release"))
        self.assertEqual(provider.available_commands(), ())
        result = provider.execute(
            self.request(),
            command_id="observe.frame",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "unsupported")
        self.assertEqual(self.transport.invocations, [])

    def test_unknown_command_is_rejected_without_transport_dispatch(self):
        result = self.provider().execute(
            self.request(),
            command_id="shell.exec",
            arguments={"command": "anything"},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "unsupported")
        self.assertEqual(self.transport.invocations, [])

    def test_observe_command_returns_only_player_observation(self):
        result = self.provider().execute(
            self.request(),
            command_id="observe.camera",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["evidence"], ["player_observation"])
        self.assertNotIn("editor_observation", result["evidence"])
        self.assertEqual(result["target_device_id"], "switch-devkit-1")

    def test_control_without_approval_is_blocked(self):
        result = self.provider().execute(
            self.request("player.mutate"),
            command_id="control.camera",
            arguments={},
            context=ResolutionContext(policy_allowed=True, approval_complete=False),
        )
        self.assertEqual(result["failure_class"], "blocked_by_approval")
        self.assertEqual(self.transport.invocations, [])

    def test_control_with_approval_requires_structured_after_state(self):
        self.transport.result = {
            "status": "passed",
            "instance_id": "player-1",
            "command_id": "control.camera",
            "project_root": self.project_root,
            "artifact_id": "artifact-1",
            "session_revision": "session-1",
            "payload": {"applied": True, "observed_state": {"fov": 60}},
        }
        result = self.provider().execute(
            self.request("player.mutate", approval=True),
            command_id="control.camera",
            arguments={"fov": 60},
            context=ResolutionContext(policy_allowed=True, approval_complete=True),
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(set(result["evidence"]), {"player_observation", "mutation_evidence"})
        self.assertIsNotNone(result["mutation_scope_fingerprint"])

    def test_control_ack_without_observed_state_is_not_mutation_evidence(self):
        self.transport.result = {
            "status": "passed",
            "instance_id": "player-1",
            "command_id": "control.quality",
            "project_root": self.project_root,
            "artifact_id": "artifact-1",
            "session_revision": "session-1",
            "payload": {"applied": True},
        }
        result = self.provider().execute(
            self.request("player.mutate", approval=True),
            command_id="control.quality",
            arguments={},
            context=ResolutionContext(policy_allowed=True, approval_complete=True),
        )
        self.assertEqual(result["failure_class"], "not_observed")
        self.assertEqual(result["evidence"], [])

    def test_runtime_project_mismatch_is_unavailable(self):
        other = str((Path(self.tmp.name) / "Other").resolve())
        self.transport.endpoints = [
            RuntimeEndpointObservation(
                "player-1", True, other, "artifact-1", "development", "1.0", "session-1"
            )
        ]
        result = self.provider().execute(
            self.request(),
            command_id="observe.runtime",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "unavailable")

    def test_runtime_artifact_mismatch_is_unavailable(self):
        self.transport.endpoints = [
            RuntimeEndpointObservation(
                "player-1", True, self.project_root, "other-artifact", "development", "1.0", "session-1"
            )
        ]
        result = self.provider().execute(
            self.request(),
            command_id="observe.runtime",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "unavailable")

    def test_catalog_revision_drift_hides_surface(self):
        provider = self.provider(artifact=self.artifact(revision="0.9"))
        self.assertEqual(provider.available_commands(), ())
        result = provider.execute(
            self.request(),
            command_id="observe.runtime",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "unsupported")

    def test_disconnect_mid_call_is_typed_unavailable(self):
        self.transport.result = {"status": "disconnected"}
        result = self.provider().execute(
            self.request(),
            command_id="observe.runtime",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "unavailable")

    def test_response_project_change_fails_closed(self):
        self.transport.result = {
            "status": "passed",
            "instance_id": "player-1",
            "command_id": "observe.runtime",
            "project_root": str((Path(self.tmp.name) / "Other").resolve()),
            "artifact_id": "artifact-1",
            "session_revision": "session-1",
            "payload": {"ok": True},
        }
        result = self.provider().execute(
            self.request(),
            command_id="observe.runtime",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "scope_violation")

    def test_stale_session_revision_fails_closed(self):
        self.transport.result = {
            "status": "passed",
            "instance_id": "player-1",
            "command_id": "observe.runtime",
            "project_root": self.project_root,
            "artifact_id": "artifact-1",
            "session_revision": "session-2",
            "payload": {"ok": True},
        }
        result = self.provider().execute(
            self.request(),
            command_id="observe.runtime",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "precondition_failed")

    def test_multiple_matching_instances_fail_closed(self):
        self.transport.endpoints = [self.endpoint, self.endpoint]
        result = self.provider().execute(
            self.request(),
            command_id="observe.runtime",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "ambiguous_binding")

    def test_player_unreachable_is_unavailable(self):
        result = self.provider(snapshot=self.snapshot(reachable=False, instance_id=None)).execute(
            self.request(),
            command_id="observe.runtime",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "unavailable")

    def test_timeout_exception_is_typed_timeout(self):
        self.transport.raise_on_invoke = TimeoutError()
        result = self.provider().execute(
            self.request(),
            command_id="observe.runtime",
            arguments={},
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["failure_class"], "timeout")


if __name__ == "__main__":
    unittest.main()
