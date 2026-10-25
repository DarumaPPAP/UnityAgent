"""実Editor起動なしでLive Gateの承認・公式CLI境界を検証する。"""
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from types import SimpleNamespace
from unityagent.persistence.store.layout import PersistenceLayout
from unittest.mock import patch

from tools import run_camera_fov_reference_live as live


class LiveUnityCliTests(unittest.TestCase):
    def test_runner_has_no_host_build_or_provider_dispatch(self):
        source = Path(live.__file__).read_text(encoding="utf-8")
        self.assertNotIn("UnityArtistCliProvider", source)
        self.assertNotIn("_publish_or_resolve_artist_cli", source)
        self.assertNotIn("explicit_unity_artist_cli", source)
        self.assertIn("execute_artist(", source)
        self.assertIn("approve_artist_execution(", source)

    def test_existing_project_cannot_use_fixture_approval(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            with patch.object(live, "_editor_path") as editor, self.assertRaisesRegex(live.LiveFailure, "fixture"):
                live.run_live(artist_root=project, project=project, scene_path="Assets/User.unity", approve_fixture_mutation=True)
            editor.assert_not_called()

    def test_success_requires_editor_payload_and_durable_broker_evidence(self):
        payload = {"status": "passed", "command": "artist.inspect"}
        result = {"status": "completed", "durable": True, "evidence_refs": ["evidence"], "provider_result": {"status": "passed", "provider_ref": "unity_cli", "payload": payload}}
        self.assertEqual(live._successful_command(result, "inspect"), payload)
        for changed in ({"durable": False}, {"status": "blocked"}, {"provider_result": {"status": "passed", "provider_ref": "other", "payload": payload}}, {"provider_result": {"status": "passed", "provider_ref": "unity_cli", "payload": {"status": "failed"}}}):
            with self.subTest(changed=changed), self.assertRaises(live.ExternalBlocker):
                live._successful_command({**result, **changed}, "inspect")

    def test_pending_real_project_never_auto_approves_and_resume_reuses_exact_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Project"
            scene = project / "Assets/Scene.unity"
            scene.parent.mkdir(parents=True)
            scene.write_bytes(b"owned fixture scene")
            capture_path = project / "capture.png"
            capture_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + b"\x00\x00\x00\x01\x00\x00\x00\x01")
            def result(command, **extra):
                payload = {"status": "passed", "command": "artist." + command, **extra}
                return {"status": "completed", "durable": True, "evidence_refs": ["evidence-" + command], "provider_result": {"status": "passed", "provider_ref": "unity_cli", "payload": payload}, "approval_plan_id": "plan-reviewed"}
            inspect = result("inspect", revision="revision", targets=[{"kind": "camera", "name": "Main Camera", "globalObjectId": "camera-guid", "fieldOfView": 40}], support={"transport": "official_unity_cli_pipeline"})
            planned = result("plan", revision="revision", approvalRequired=True, planId="plan-reviewed")
            observed = []
            def execute(plane, project, run_id, command, **kwargs):
                observed.append(command.name)
                if command.name == "plan":
                    return planned
                if command.name == "apply" and not kwargs.get("approval_ref"):
                    raise ValueError("explicit approval required")
                return result(command.name, colorPath=str(capture_path))
            with patch.object(live, "_editor_path", return_value=Path("Editor")), patch.object(live, "_find_executable", return_value=Path("unity")), patch.object(live, "_open_editor", return_value={}), patch.object(live, "_open_scene", return_value={}) as open_scene, patch.object(live, "_inspect_when_ready", return_value=inspect), patch.object(live, "_execute", side_effect=execute), patch.object(live, "approve_artist_execution") as approve, patch.object(live, "verify_live_evidence", return_value={"status": "passed"}):
                with self.assertRaises(live.ExternalBlocker) as blocked:
                    live.run_live(artist_root=root, project=project, scene_path="Assets/Scene.unity", state_root=root / "state", run_id="test-run")
                self.assertEqual(blocked.exception.evidence["approval_plan_id"], "plan-reviewed")
                self.assertEqual(observed, ["plan", "preview", "apply"])
                approve.assert_not_called()
                report = live.run_live(artist_root=root, project=project, scene_path="Assets/Scene.unity", state_root=root / "state", run_id="test-run", approval_ref="human-approved-plan")
                self.assertEqual(report["status"], "passed")
                self.assertEqual(observed.count("plan"), 1)
                self.assertEqual(open_scene.call_count, 1)
                approve.assert_not_called()

    def test_persisted_payload_rechecks_raw_digest_and_run_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            layout = PersistenceLayout(temporary)
            payload = {"status": "passed", "command": "artist.inspect"}
            raw = {"status": "passed", "provider_ref": "unity_cli", "payload": payload}
            path = layout.snapshot("run", "provider-result", live.sha256_json(raw))
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(raw), encoding="utf-8")
            result = {"status": "completed", "durable": True, "evidence_refs": ["id"], "provider_result": raw}
            record = {"durability": "durable", "verification_status": "passed", "provider_ref": "unity_cli", "project_root": temporary, "payload_ref": path.relative_to(layout.root).as_posix()}
            store = SimpleNamespace(layout=layout, verify_record=lambda *args, **kwargs: record)
            self.assertEqual(live._persisted_payload(store, result, "run", temporary, "inspect"), payload)
            path.write_text(json.dumps({**raw, "extra": "tampered"}), encoding="utf-8")
            with self.assertRaisesRegex(live.LiveFailure, "digest"):
                live._persisted_payload(store, result, "run", temporary, "inspect")
            record["payload_ref"] = "../outside.json"
            with self.assertRaisesRegex(live.LiveFailure, "escapes"):
                live._persisted_payload(store, result, "run", temporary, "inspect")

    def test_fixture_cleanup_matches_project_argument_instead_of_path_substring(self):
        with patch.object(live.os, "name", "nt"), patch.object(live.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "[]", "")) as run:
            live._stop_fixture_editor(Path("C:/Fixtures/Artist"))
        script = run.call_args.args[0][-1]
        self.assertIn("-projectPath", script)
        self.assertIn("-match $targetPattern", script)
        self.assertNotIn(".Contains($target)", script)

    def test_final_gate_targets_authority_harness_without_host(self):
        source = (Path(live.__file__).parent / "reference_implementation_final_gate.py").read_text(encoding="utf-8")
        self.assertNotIn("tools/host", source)
        self.assertIn("AuthorityClientTests.csproj", source)
        self.assertIn("verify_live_evidence", source)
