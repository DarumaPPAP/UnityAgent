"""Contract tests for the fixed, approval gated Unity Editor E2E probe."""
from __future__ import annotations

import json
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from ControlPlane.full_e2e import SCRIPT_TEMPLATE, apply_full_e2e
from Persistence.Approval.approval_store import ApprovalDecisionStore
from Runtime.Tooling.Providers.UnityAgentEditor.full_e2e_provider import FullE2EEditorProvider
from Tools.unity_agent_cli import _fingerprint
from Runtime.Tooling.Environment.discovery import discover_environment
from Runtime.Tooling.Environment.environment_snapshot import UnityCliSnapshot
from Runtime.Tooling.Environment.native_editor_discovery import EditorCandidate, EditorProcessObservation
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.tool_broker import ToolBroker


ROOT = Path(__file__).resolve().parents[2]


class FullE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name) / "Project"
        for name in ("Assets", "Packages", "ProjectSettings"):
            (self.project / name).mkdir(parents=True)
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.3.15f1\n", encoding="utf-8"
        )
        (self.project / "Packages/manifest.json").write_text(
            '{"dependencies":{"com.darumappap.unity-agent":"file:/unityagent"}}', encoding="utf-8"
        )
        self.state = Path(self.directory.name) / "State"

    def cli(self, *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "Tools/unity_agent_cli.py"), "e2e", *arguments,
             "--project-path", str(self.project), "--state-root", str(self.state)],
            capture_output=True, text=True, cwd=ROOT, check=False,
        )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            result = {"stdout": completed.stdout, "stderr": completed.stderr}
        return completed, result

    def test_plan_previews_exact_assets_without_mutating_project(self) -> None:
        self.assertEqual(SCRIPT_TEMPLATE.read_bytes(), (ROOT / "Packages/com.darumappap.unity-agent/Editor/Resources/FullE2EProbe.txt").read_bytes())
        completed, plan = self.cli("plan")
        self.assertEqual(completed.returncode, 0, plan)
        self.assertEqual(plan["status"], "planned")
        self.assertTrue(plan["approval_required"])
        self.assertEqual(
            {item["path"] for item in plan["exact_diff"]},
            {
                "Assets/UnityAgentE2E.meta",
                "Assets/UnityAgentE2E/FullE2EScene.unity",
                "Assets/UnityAgentE2E/FullE2EScene.unity.meta",
                "Assets/UnityAgentE2E/FullE2EMaterial.mat",
                "Assets/UnityAgentE2E/FullE2EMaterial.mat.meta",
                "Assets/UnityAgentE2E/FullE2EProbe.cs",
                "Assets/UnityAgentE2E/FullE2EProbe.cs.meta",
            },
        )
        self.assertFalse((self.project / "Assets/UnityAgentE2E").exists())
        self.assertFalse((self.project / "Assets/UnityAgentE2E.meta").exists())
        self.assertIn("class FullE2EProbe", plan["script_preview"])
        self.assertEqual(plan["scene_object_diff"]["name"], "FullE2EProbeCube")
        self.assertEqual(plan["scene_object_diff"]["material_path"], plan["material_path"])
        self.assertEqual(plan["target_preimage"], "absent")
        self.assertIn("Unity Editor", plan["undo_path"])
        self.assertIn("Unlit/Color", plan["material_shader_candidates"])

    def test_state_root_inside_project_is_rejected_before_plan(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "Tools/unity_agent_cli.py"), "e2e", "plan",
             "--project-path", str(self.project), "--state-root", str(self.project / "E2EState")],
            capture_output=True, text=True, cwd=ROOT, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["status"], "blocked")
        self.assertFalse((self.project / "E2EState").exists())

    def test_approval_is_bound_to_immutable_plan_and_not_a_freeform_ref(self) -> None:
        _, plan = self.cli("plan")
        rejected, invalid = self.cli("approve", "--plan-id", "0" * 64)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(invalid.get("status"), "blocked", invalid)
        approved, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        self.assertEqual(approved.returncode, 0, decision)
        self.assertEqual(decision["status"], "approved")
        self.assertEqual(decision["plan_id"], plan["plan_id"])
        self.assertTrue(decision["approval_ref"])
        saved, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        self.assertEqual(saved.returncode, 0, save_decision)
        self.assertNotEqual(save_decision["save_approval_ref"], decision["approval_ref"])

    def test_mutation_approval_alone_cannot_authorize_scene_save(self) -> None:
        _, plan = self.cli("plan")
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        completed, rejected = self.cli("apply", "--plan-id", plan["plan_id"],
                                       "--approval-ref", decision["approval_ref"])
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(rejected.get("status"), "blocked", rejected)
        self.assertIn("save", rejected.get("reason", "").lower())
        self.assertFalse((self.project / "Assets/UnityAgentE2E").exists())

    def test_apply_does_not_accept_untrusted_approval_or_stale_plan(self) -> None:
        _, plan = self.cli("plan")
        no_approval, rejected = self.cli("apply", "--plan-id", plan["plan_id"], "--approval-ref", "invented")
        self.assertNotEqual(no_approval.returncode, 0)
        self.assertEqual(rejected.get("status"), "blocked", rejected)
        self.assertFalse((self.project / "Assets/UnityAgentE2E").exists())
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        _, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        (self.project / "Assets/UnityAgentE2E").mkdir()
        stale, rejected = self.cli("apply", "--plan-id", plan["plan_id"], "--approval-ref", decision.get("approval_ref", "missing"),
                                   "--save-approval-ref", save_decision.get("save_approval_ref", "missing"))
        self.assertNotEqual(stale.returncode, 0)
        self.assertEqual(rejected["status"], "blocked")

    def test_editor_unavailable_cannot_produce_full_e2e_success(self) -> None:
        _, plan = self.cli("plan")
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        _, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        completed, result = self.cli("apply", "--plan-id", plan["plan_id"], "--approval-ref", decision.get("approval_ref", "missing"),
                                     "--save-approval-ref", save_decision.get("save_approval_ref", "missing"))
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(result["status"], "blocked")
        self.assertIn(result["compile"], ("not_observed", "unavailable"))
        self.assertIn(result["playmode"], ("not_observed", "unavailable"))
        self.assertTrue(Path(result["artifact_path"]).is_file())
        self.assertFalse((self.project / "Assets/UnityAgentE2E").exists())

    def test_python_heartbeat_cannot_impersonate_a_live_unity_editor(self) -> None:
        _, plan = self.cli("plan")
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        _, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        self.fake_editor(plan, create_files=False, start_worker=False)
        completed, result = self.cli("apply", "--plan-id", plan["plan_id"],
                                     "--approval-ref", decision["approval_ref"],
                                     "--save-approval-ref", save_decision["save_approval_ref"],
                                     "--timeout-seconds", "1")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Unity", result["reason"])
        self.assertFalse((self.project / "Library/UnityAgent/full_e2e/jobs").exists())

    def test_policy_denial_blocks_even_with_both_valid_approvals(self) -> None:
        _, plan = self.cli("plan")
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        _, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        with patch("ControlPlane.full_e2e.policy_for_capability", return_value={"default_permission": "prohibited"}):
            with self.assertRaisesRegex(ValueError, "Policy"):
                apply_full_e2e(self.project, self.state, plan["plan_id"], decision["approval_ref"],
                               save_decision["save_approval_ref"], definition_fingerprint={})
        self.assertFalse((self.project / "Assets/UnityAgentE2E").exists())

    def test_broker_resolves_only_the_fixed_e2e_workflow_to_editor_bridge(self) -> None:
        snapshot = discover_environment(
            str(self.project),
            editor_candidates=[EditorCandidate("/fake/Unity", "6000.3.15f1")],
            editor_processes=[EditorProcessObservation(123, "/fake/Unity", "", str(self.project), False)],
            unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"),
            which_fn=lambda name: None,
        )
        request = {
            "schema_version": "1.0", "capability": "scene.mutate", "project_root": str(self.project),
            "operation_kind": "editor_mutation", "required_evidence": [
                "editor_observation", "mutation_evidence", "compile_observation", "test_execution"],
            "mutation_scope": {"allowed_paths": ["Assets/UnityAgentE2E", "Assets/UnityAgentE2E.meta"],
                               "prohibited_paths": ["ProjectSettings"]},
            "approval_ref": "approved-ref", "preferred_surface": "live_editor",
            "qualifiers": {"workflow": "full_e2e"},
        }
        context = ResolutionContext(policy_allowed=True, approval_complete=True, approval_required=True)
        resolved = ToolBroker().resolve(request, snapshot, context=context)
        self.assertEqual(resolved["provider_ref"], "unity_agent_editor", resolved)
        without_workflow = ToolBroker().resolve({**request, "qualifiers": None}, snapshot, context=context)
        self.assertNotEqual(without_workflow.get("provider_ref"), "unity_agent_editor")

    def fake_editor(self, plan: dict, *, create_files: bool, editor_failed: bool = False, extra_asset: bool = False,
                    revoke_ref: str | None = None,
                    start_worker: bool = True) -> threading.Thread | None:
        bridge = self.project / "Library/UnityAgent/full_e2e"
        bridge.mkdir(parents=True)
        secret = b"fixed-test-secret-with-32-bytes...."
        (bridge / "bridge.key").write_text(base64.b64encode(secret).decode("ascii"), encoding="ascii")
        (bridge / "heartbeat.json").write_text(json.dumps({
            "schema_version": "1.0", "project_root": str(self.project),
            "editor_version": "6000.3.15f1", "editor_path": sys.executable,
            "process_id": os.getpid(), "instance_id": "fixture-editor-1", "safe_mode": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }), encoding="utf-8")

        def respond() -> None:
            jobs = bridge / "jobs"
            for _ in range(250):
                pending = sorted(jobs.glob("*.json")) if jobs.exists() else []
                if pending:
                    job = json.loads(pending[0].read_text(encoding="utf-8"))
                    if revoke_ref:
                        ApprovalDecisionStore(self.state).revoke(revoke_ref)
                    if create_files:
                        for item in plan["exact_diff"]:
                            target = self.project / item["path"]
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(
                                (ROOT / "Packages/com.darumappap.unity-agent/Editor/Resources/FullE2EProbe.txt").read_bytes()
                                if target.suffix == ".cs" else b"fixture\n"
                            )
                        if extra_asset:
                            (self.project / "Assets/UnityAgentE2E/Unexpected.asset").write_bytes(b"unexpected")
                    paths = [item["path"] for item in plan["exact_diff"]]
                    result = {
                        "schema_version": "1.0", "run_id": job["run_id"], "project_root": job["project_root"],
                        "plan_id": job["plan_id"], "approval_ref": job["approval_ref"],
                        "save_approval_ref": job["save_approval_ref"],
                        "status": "failed" if editor_failed else "passed", "compile": "passed",
                        "playmode": "failed" if editor_failed else "passed",
                        "script_sha256": plan["script_sha256"], "changed_paths": paths,
                        "object_name": "FullE2EProbeCube", "instance_id": "fixture-editor-1",
                        "shader_name": "Unlit/Color",
                        "reason": "Probe Start did not run" if editor_failed else None,
                    }
                    material = "\n".join("" if result[key] is None else str(result[key]) for key in (
                        "run_id", "project_root", "plan_id", "approval_ref", "save_approval_ref", "status", "compile",
                        "playmode", "script_sha256", "object_name", "instance_id", "shader_name", "reason")) + "\n" + ",".join(paths)
                    result["signature"] = hmac.new(secret, material.encode("utf-8"), hashlib.sha256).hexdigest()
                    output = bridge / "results" / (job["run_id"] + ".json")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text(json.dumps(result), encoding="utf-8")
                    return
                time.sleep(0.02)

        if not start_worker:
            return None
        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        return thread

    def mocked_apply(self, plan: dict, decision: dict, save_decision: dict) -> dict:
        # Test harness only: the subprocess CLI never replaces OS Editor discovery.
        with patch.object(FullE2EEditorProvider, "_process_matches", return_value=True):
            return apply_full_e2e(self.project, self.state, plan["plan_id"], decision["approval_ref"],
                                  save_decision["save_approval_ref"],
                                  definition_fingerprint=_fingerprint(), timeout_seconds=4)

    def test_broker_persists_evidence_only_for_signed_result_and_real_assets(self) -> None:
        _, plan = self.cli("plan")
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        _, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        worker = self.fake_editor(plan, create_files=True)
        result = self.mocked_apply(plan, decision, save_decision)
        worker.join(timeout=1)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["compile"], "passed")
        self.assertEqual(result["playmode"], "passed")
        self.assertEqual(result["material_shader"], "Unlit/Color")
        self.assertEqual(len(result["evidence_refs"]), 1)
        self.assertTrue(Path(result["artifact_path"]).is_file())

    def test_signed_editor_claim_without_assets_remains_blocked(self) -> None:
        _, plan = self.cli("plan")
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        _, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        worker = self.fake_editor(plan, create_files=False)
        result = self.mocked_apply(plan, decision, save_decision)
        worker.join(timeout=1)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["playmode"], "reported_passed_unverified")

    def test_signed_result_with_undeclared_scoped_asset_is_blocked(self) -> None:
        _, plan = self.cli("plan")
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        _, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        worker = self.fake_editor(plan, create_files=True, extra_asset=True)
        result = self.mocked_apply(plan, decision, save_decision)
        worker.join(timeout=1)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("undeclared", result["reason"])
        self.assertTrue(Path(result["editor_result_artifact_path"]).is_file())
        self.assertEqual(result["scene"], "created")
        self.assertEqual(result["compile"], "reported_passed_unverified")

    def test_revocation_after_dispatch_cannot_complete_evidence(self) -> None:
        _, plan = self.cli("plan")
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        _, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        worker = self.fake_editor(plan, create_files=True, revoke_ref=save_decision["save_approval_ref"])
        result = self.mocked_apply(plan, decision, save_decision)
        worker.join(timeout=1)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["playmode"] == "passed")

    def test_editor_failure_retains_signed_result_artifact_and_actual_observations(self) -> None:
        _, plan = self.cli("plan")
        _, decision = self.cli("approve", "--plan-id", plan["plan_id"])
        _, save_decision = self.cli("approve-save", "--plan-id", plan["plan_id"])
        worker = self.fake_editor(plan, create_files=True, editor_failed=True)
        result = self.mocked_apply(plan, decision, save_decision)
        worker.join(timeout=1)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["compile"], "passed")
        self.assertEqual(result["playmode"], "failed")
        self.assertEqual(result["reason"], "Probe Start did not run")
        self.assertTrue(Path(result["editor_result_artifact_path"]).is_file())
        self.assertEqual(result["scene"], "created")
        self.assertEqual(result["gameobject"], "created")
        self.assertEqual(result["material"], "created")
        self.assertEqual(result["script"], "created")


if __name__ == "__main__":
    unittest.main()
