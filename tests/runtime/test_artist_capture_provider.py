from __future__ import annotations

import copy
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand
from tests.runtime import test_artist_command_adapter as artist_fixture


class ArtistCaptureProviderTests(unittest.TestCase):
    def setUp(self):
        self.boundary = artist_fixture.ArtistProviderBoundaryTests()
        self.boundary.setUp()
        self.addCleanup(self.boundary.doCleanups)
        self.command = ArtistCommand("capture", request_json='{"captureCameraName":"Main Camera"}')
        self.boundary.request.update(capability="visual.capture", required_evidence=["visual_capture", "camera_binding", "capture_manifest"], qualifiers={"domain": "visual_art", "workflow": "capture"})
        self.boundary.discovery = replace(self.boundary.discovery, command_catalog=({"name": "artist.capture", "runtime_only": False},))
        self.editor = copy.deepcopy(next(item["editor_result"] for item in artist_fixture.BASELINE["commands"] if item["command"] == "capture"))
        self.editor.update(captureId="capture-provider-test", revision="revision-before", baseRevision="revision-before")
        self.image = self.boundary.root / "Library/UnityArtist/Captures/capture-provider-test/color.png"
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"capture-file")
        self.editor["evidence"] = ["visual_capture", "camera_binding:Main Camera", "capture_manifest", "color_path:" + str(self.image)]

    def run_capture(self):
        result = {"status": "passed", "result": SimpleNamespace(returncode=0, stdout=artist_fixture.output(self.editor, self.boundary.root))}
        with patch.object(self.boundary.provider, "dispatch_fn", return_value=result) as dispatch:
            mapped = self.boundary.run_command(self.command)
        return mapped, dispatch

    def test_read_capture_uses_unity_cli_without_a_host_and_observes_real_artifact(self):
        result, dispatch = self.run_capture()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["provider_ref"], "unity_cli")
        self.assertEqual(result["host_file_observation"]["bytes"], 12)
        self.assertIn("artist.capture", dispatch.call_args.args[0].command)
        self.assertNotIn("unity_artist_cli", self.boundary.snapshot)

    def test_capture_is_not_accepted_under_scene_inspection_or_without_explicit_camera(self):
        self.boundary.request.update(capability="scene.inspect", required_evidence=["editor_observation"])
        result, dispatch = self.run_capture()
        self.assertEqual(result["status"], "failed")
        dispatch.assert_not_called()
        self.boundary.request.update(capability="visual.capture", required_evidence=["visual_capture"])
        self.command = ArtistCommand("capture")
        result, dispatch = self.run_capture()
        self.assertEqual(result["status"], "failed")
        dispatch.assert_not_called()
