from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand
from unityagent.runtime.tooling.providers.unity_cli.artist_result_mapper import normalize_artist_pipeline_result


class ArtistCaptureMapperTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.image = self.root / "Library/UnityArtist/Captures/artist-capture-test/color.png"
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"abc")
        self.command = ArtistCommand("capture", request_json='{"captureCameraName":"Main Camera"}')
        self.editor = {"schemaVersion": "2.0", "product": "UnityArtistCLI", "command": "artist.capture", "status": "passed", "verified": True, "revision": "current", "baseRevision": "current", "approvalRequired": False, "savePerformed": False, "undoAvailable": True, "humanReview": False, "support": {"supported": True, "unityVersion": "6000.3.12f1", "renderPipeline": "urp"}, "exactDiff": [], "targets": [], "errors": [], "captureId": "artist-capture-test", "evidence": ["visual_capture", "camera_binding:Main Camera", "capture_manifest", "color_path:" + str(self.image)]}

    def map(self, *, editor=None, command=None, root=None, **kwargs):
        envelope = {"success": True, "command": "command", "errors": [], "data": {"target": {"projectPath": str(root or self.root)}, "result": json.dumps(self.editor if editor is None else editor)}}
        return normalize_artist_pipeline_result(exit_code=kwargs.pop("exit_code", 0), stdout=json.dumps(envelope), command=command or self.command, project_root=self.root, unity_version="6000.3.12f1", render_pipeline="urp", **kwargs)

    def test_capture_observes_real_file_without_forging_editor_hash_or_acceptance(self):
        result = self.map()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["capture_id"], "artist-capture-test")
        self.assertEqual(result["camera_binding"], "Main Camera")
        self.assertEqual(result["host_file_observation"], {"source": "host_file_observation", "color_path": str(self.image.resolve()), "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "bytes": 3})
        self.assertEqual(result["payload"], self.editor)
        self.assertNotIn("human_visual_acceptance", result["evidence"])

    def test_request_camera_must_be_explicit_and_match_single_editor_binding(self):
        for request in (None, "{}", '{"captureCameraName":true}', '{"captureCameraName":"Other Camera"}'):
            with self.subTest(request=request):
                self.assertEqual(self.map(command=ArtistCommand("capture", request_json=request))["status"], "failed")
        for extra in ("camera_binding:Other Camera", "camera_binding:Main Camera", "color_path:" + str(self.image)):
            editor = copy.deepcopy(self.editor)
            editor["evidence"].append(extra)
            self.assertEqual(self.map(editor=editor)["status"], "failed")

    def test_missing_empty_outside_or_escaped_capture_files_never_pass(self):
        for path in (self.image.parent / "missing.png", self.root / "outside.png", self.image.parent / ".." / "artist-capture-test" / "color.png"):
            editor = copy.deepcopy(self.editor)
            editor["evidence"][-1] = "color_path:" + str(path)
            self.assertEqual(self.map(editor=editor)["status"], "failed")
        self.image.write_bytes(b"")
        self.assertEqual(self.map()["status"], "failed")

    def test_inner_failures_malformed_types_revision_and_project_are_rejected(self):
        for key, value in (("status", "unknown"), ("verified", False), ("verified", "true"), ("captureId", "../escape"), ("captureId", True), ("revision", "changed"), ("targets", {}), ("evidence", {}), ("humanReview", True), ("errors", [{"code": "CAPTURE_FAILED"}])):
            editor = copy.deepcopy(self.editor)
            editor[key] = value
            with self.subTest(key=key, value=value):
                self.assertEqual(self.map(editor=editor)["status"], "failed")
        editor = copy.deepcopy(self.editor)
        editor.update(status="failed", errors=[{"code": "CAPTURE_FAILED", "message": "Camera failed"}])
        self.assertEqual(self.map(editor=editor)["error_code"], "CAPTURE_FAILED")
        self.assertEqual(self.map(root=self.root / "another")["failure_class"], "scope_violation")
        self.assertEqual(self.map(exit_code=1)["status"], "failed")

    def test_symlink_escape_is_rejected(self):
        outside = self.root / "outside.png"
        outside.write_bytes(b"abc")
        self.image.unlink()
        try:
            self.image.symlink_to(outside)
        except OSError as exc:
            self.skipTest("Symbolic links unavailable: " + str(exc))
        self.assertEqual(self.map()["status"], "failed")

    @unittest.skipUnless(os.name == "nt", "Windows junction contract")
    def test_directory_junction_cannot_redirect_capture_storage(self):
        actual = self.root / "redirected"
        library = self.root / "Library"
        library.rename(actual)
        completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(library), str(actual)], capture_output=True)
        if completed.returncode != 0:
            self.skipTest("Junction creation unavailable: " + completed.stderr.decode(errors="replace"))
        self.addCleanup(library.rmdir)
        self.assertEqual(self.map()["status"], "failed")

    def test_human_decision_and_mutation_remain_unobserved(self):
        for command in (ArtistCommand("evaluate", capture_id="capture", decision="accepted"), ArtistCommand("refine", evaluation_id="eval", request_json="{}"), ArtistCommand("apply", plan_id="plan", expected_revision="current", approval_token="token")):
            self.assertEqual(self.map(command=command)["status"], "failed")
