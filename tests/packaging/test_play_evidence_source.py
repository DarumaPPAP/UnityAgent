"""Editor Play capture package boundary checks (not an actual Unity Editor test)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Packages/com.darumappap.unity-agent/Editor/PlayEvidenceWindow.cs"
SETUP = ROOT / "Packages/com.darumappap.unity-agent/Editor/SetupWindow.cs"


class PlayEvidenceSourceTests(unittest.TestCase):
    def test_editor_entry_and_meta_are_packaged(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertTrue(SOURCE.with_suffix(".cs.meta").is_file())
        self.assertIn('[MenuItem("UnityAgent/Play Evidence")]', source)
        self.assertIn("PlayEvidenceWindow.Open();", SETUP.read_text(encoding="utf-8"))

    def test_capture_never_promotes_visual_to_e2e_pass(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("ScreenCapture.CaptureScreenshot(", source)
        self.assertIn('visual_acceptance = "human_review_required"', source)
        self.assertIn('e2e_gate = "not_assessed"', source)
        self.assertIn('capture_kind = "editor_play"', source)
        self.assertNotIn("BuildPipeline.BuildPlayer", source)

    def test_recorder_optional_without_implicit_install(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('RequireRecorderType("UnityEditor.Recorder.RecorderController")', source)
        self.assertIn('RequireRecorderType("UnityEditor.Recorder.MovieRecorderSettings")', source)
        self.assertIn('Enum.Parse(outputFormat.PropertyType, "MP4")', source)
        self.assertNotIn("Client.Add(", source)


if __name__ == "__main__":
    unittest.main()
