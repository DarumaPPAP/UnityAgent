from __future__ import annotations

import sys
import shutil
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ControlPlane.unity_agent_control_plane import UnityAgentControlPlane
from Runtime.Tooling.Environment.discovery import discover_environment
from Runtime.Tooling.Environment.environment_snapshot import UnityCliSnapshot
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.Providers.Installer.installer_provider import InstallerProvider


def fingerprint() -> dict[str, str]:
    return {
        "schema_version": "1.0",
        "architecture_version": "five-layer-v1",
        "policy_revision": "policy-v1",
        "prompt_revision": "prompt-v1",
        "context_revision": "context-v1",
        "graph_revision": "graph-v1",
        "runtime_profile_revision": "runtime-v1",
        "tool_schema_revision": "tool-v1",
        "checkpoint_schema_revision": "checkpoint-v1",
        "evidence_schema_revision": "evidence-v1",
        "eval_contract_revision": "eval-v1",
    }


class ControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / f".tmp-control-plane-{uuid.uuid4().hex}"
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.project = self.root / "Project"
        (self.project / "Assets").mkdir(parents=True)
        (self.project / "Packages").mkdir()
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.3.15f1\n", encoding="utf-8"
        )
        (self.project / "Packages/manifest.json").write_text(
            '{"dependencies": {"com.unity.pipeline": "1.0.0"}}', encoding="utf-8"
        )
        self.snapshot = discover_environment(
            str(self.project),
            editor_candidates=[],
            editor_candidates_observed=True,
            editor_processes=[],
            editor_processes_observed=True,
            unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"),
            provider_instances={"myunitymcp": [], "coplay_mcp": []},
            which_fn=lambda name: "/usr/bin/git" if name == "git" else None,
        ).to_dict()

    def entry_request(self) -> dict:
        return {
            "schema_version": "1.0",
            "request_id": "inspect-1",
            "entry_point": "codex_plugin",
            "project_root": str(self.project.resolve()),
            "intent": {"kind": "project_inspection"},
            "route_id": "inspect_project",
            "node_id": "inspect-project",
            "loop_id": "inspect-loop",
            "execution_profile": "generic_planning",
            "context_id": "context-1",
            "context_fingerprint": "context-fingerprint-1",
            "task_contract_runtime_projection": {},
            "mutation_scope": {},
            "validation_requirements": ["project_fact"],
            "capability_requests": [{
                "schema_version": "1.0",
                "capability": "project.inspect",
                "project_root": str(self.project.resolve()),
                "operation_kind": "read",
                "required_evidence": ["project_fact"],
                "mutation_scope": None,
                "approval_ref": None,
                "preferred_surface": "project",
            }],
        }

    def test_execution_facade_owns_run_and_persists_evidence(self) -> None:
        plane = UnityAgentControlPlane(self.root / "state")
        result = plane.execute(
            self.entry_request(),
            environment_snapshot=self.snapshot,
            context=ResolutionContext(policy_allowed=True),
            executors={
                "file": lambda request, context, arguments: {
                    "status": "passed",
                    "failure_class": None,
                    "provider_ref": "file",
                    "evidence": ["project_fact"],
                }
            },
            definition_fingerprint=fingerprint(),
            run_id="run-control-plane-1",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["layer_trace"][0:2], ["entry", "control_plane"])
        self.assertEqual(len(result["evidence_refs"]), 1)
        state = plane.state_store.load_execution_state(result["run_id"])
        self.assertEqual(state["status"], "completed")
        loop = plane.state_store.load_loop_control_state(result["run_id"], "inspect-loop")
        self.assertEqual(loop["decision"], "exit")
        evidence = plane.evidence_store.get(result["evidence_refs"][0])
        self.assertEqual(evidence["provider_ref"], "file")
        self.assertEqual(evidence["durability"], "durable")

    def test_setup_uses_registry_resolved_installer_and_evidence(self) -> None:
        (self.project / "Packages/manifest.json").write_text(
            '{"dependencies": {"com.darumappap.unity-artist": "0.0.1-beta"}}', encoding="utf-8"
        )
        installer = InstallerProvider(
            self.project,
            which_fn=lambda name: "/tools/unity.exe" if name in {"unity", "unity-artist"} else None,
            env={},
        )
        plane = UnityAgentControlPlane(self.root / "setup-state")
        result = plane.setup(
            "codex_plugin",
            {
                "schema_version": "1.0",
                "request_id": "doctor-1",
                "operation": "doctor",
                "project_root": str(self.project.resolve()),
                "products": ["official_unity_cli", "unity_artist_cli"],
                "channel": "0.0.6-beta",
                "non_interactive": True,
            },
            executors={"installer": installer.execute},
            definition_fingerprint=fingerprint(),
            run_id="run-setup-1",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["operation"], "doctor")
        self.assertEqual(len(result["evidence_refs"]), 1)
        self.assertEqual(plane.evidence_store.get(result["evidence_refs"][0])["producer"], "installer_provider")

    def test_approved_setup_persists_install_receipt_after_evidence_id_is_known(self) -> None:
        receipt_entry = {
            "product": "unity_artist_cli",
            "status": "installed",
            "version": "0.0.1-beta",
            "location": "C:/Users/test/AppData/Local/UnityArtistCLI/Beta/unity-artist.exe",
            "source": "github:DarumaPPAP/UnityArtistCLI@v0.0.1-beta",
            "sha256": "sha256:" + "a" * 64,
        }
        installer = InstallerProvider(
            self.project,
            installer_fn=lambda plan: {
                "schema_version": "1.0",
                "operation": "apply",
                "status": "passed",
                "project_root": str(self.project.resolve()),
                "channel": "0.0.6-beta",
                "install_receipt": {
                    "schema_version": "1.0",
                    "receipt_id": "receipt-approved",
                    "run_id": "pending",
                    "project_root": str(self.project.resolve()),
                    "channel": "0.0.6-beta",
                    "entries": [receipt_entry],
                    "verified_at": "2026-09-11T00:00:00+00:00",
                    "evidence_refs": [],
                },
            },
            env={},
        )
        plane = UnityAgentControlPlane(self.root / "receipt-state")
        result = plane.setup(
            "unity_ui",
            {
                "schema_version": "1.0",
                "request_id": "apply-1",
                "operation": "apply",
                "project_root": str(self.project.resolve()),
                "products": ["unity_artist_cli"],
                "channel": "0.0.6-beta",
                "non_interactive": True,
                "approval_ref": "approval-1",
                "expected_plan_id": "plan-approved",
            },
            executors={"installer": installer.execute},
            executor_arguments={
                "approval_complete": True,
                "approved_plan": {
                    "plan_id": "plan-approved",
                    "project_root": str(self.project.resolve()),
                    "actions": [{"product": "unity_artist_cli", "action": "install_then_verify"}],
                },
            },
            definition_fingerprint=fingerprint(),
            run_id="run-receipt-1",
        )
        self.assertEqual(result["status"], "completed")
        self.assertIsNotNone(result["receipt_ref"])
        self.assertEqual(
            plane.receipt_store.get("receipt-approved")["evidence_refs"],
            [result["evidence_refs"][0]],
        )


if __name__ == "__main__":
    unittest.main()
