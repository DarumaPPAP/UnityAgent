"""Verify bundled Editor Play/Timeline MediaEncoder contract without claiming Unity execution."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "Packages/com.darumappap.unity-agent/Editor"
WINDOW = EDITOR / "PlayEvidenceWindow.cs"
ENCODER = EDITOR / "PlayVideoEncoder.cs"
SETUP = EDITOR / "SetupWindow.cs"


class PlayEvidenceSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = WINDOW.read_text(encoding="utf-8")
        cls.encoder = ENCODER.read_text(encoding="utf-8")

    def test_package_has_editor_entry_and_meta(self):
        for path in (WINDOW, ENCODER):
            self.assertTrue(path.with_suffix(".cs.meta").is_file(), str(path))
        self.assertIn('[MenuItem("UnityAgent/Play Evidence")]', self.window)
        self.assertIn("PlayEvidenceWindow.Open();", SETUP.read_text(encoding="utf-8"))

    def test_media_encoder_is_direct_and_package_free(self):
        self.assertIn("using UnityEditor.Media;", self.encoder)
        self.assertIn("new MediaEncoder(outputPath, video)", self.encoder)
        self.assertIn("encoder.AddFrame(frameTexture)", self.encoder)
        self.assertIn("encoder.Dispose()", self.encoder)
        self.assertNotIn("UnityEditor.Recorder", self.window + self.encoder)
        self.assertNotIn("Client.Add(", self.window + self.encoder)

    def test_recording_has_bounded_session_and_video_evidence(self):
        for field in (
            "DurationReached", "SkippedFrames", "RepeatedFrames",
            "IsPlausibleMp4", "video_stopped_by", "video_sha256",
            "video_timing = \"realtime_not_frame_exact\"",
        ):
            self.assertIn(field, self.window + self.encoder)
        self.assertIn("StopRecording(\"play_mode_exit\")", self.window)
        self.assertIn("StopRecording(\"window_closed_or_reload\")", self.window)

    def test_timeline_control_respects_play_mode(self):
        self.assertIn("PlayableDirector", self.window)
        self.assertIn("director.time = 0;", self.window)
        self.assertIn("director.Evaluate();", self.window)
        self.assertIn("director.Play();", self.window)
        self.assertIn("director.stopped += OnTimelineStopped;", self.window)
        self.assertIn("StopRecording(\"timeline_finished\")", self.window)
        self.assertLess(self.window.index("director.Stop();"),
                        self.window.index("director.stopped += OnTimelineStopped;"))

    def test_capture_cannot_promote_visual_to_e2e(self):
        self.assertIn("ScreenCapture.CaptureScreenshot(", self.window)
        self.assertIn('visual_acceptance = "human_review_required"', self.window)
        self.assertIn('e2e_gate = "not_assessed"', self.window)
        self.assertIn('capture_kind = "editor_play"', self.window)
        self.assertNotIn("BuildPipeline.BuildPlayer", self.window + self.encoder)

    def test_does_not_throttle_video_capture_to_evidence_writes(self):
        head = self.window.split("private void UpdateCapture()", 1)[1]
        tick = head.index("recorder.Tick();")
        poll = head.index("EditorApplication.timeSinceStartup < nextPoll")
        self.assertLess(tick, poll, "video tick must not be gated by evidence polling")
        self.assertIn("nextPoll = EditorApplication.timeSinceStartup + 0.25;", head)

    def test_private_play_mode_view_api_is_confined(self):
        self.assertIn('"UnityEditor.PlayModeView"', self.encoder)
        self.assertIn('"m_TargetTexture"', self.encoder)
        self.assertNotIn("PlayModeView", self.window)
        self.assertIn("RenderTexture.active = previous", self.encoder)
        self.assertIn("readbackTarget.Release()", self.encoder)


if __name__ == "__main__":
    unittest.main()
