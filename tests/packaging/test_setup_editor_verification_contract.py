"""UnityAgent Setupのバージョン確認とP9検証UIの静的安全契約。実Editor実行は別Gate。"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "Packages/com.darumappap.unity-agent/Editor"
SETUP = (EDITOR / "SetupWindow.cs").read_text(encoding="utf-8")
PANEL = (EDITOR / "SetupVerificationPanel.cs").read_text(encoding="utf-8")


class SetupEditorVerificationContractTests(unittest.TestCase):
    def test_existing_setup_window_is_canonical_ui(self):
        self.assertIn('[MenuItem("UnityAgent/Setup")]', SETUP)
        self.assertIn("SetupVerificationPanel.Draw();", SETUP)
        self.assertIn('DrawEnvironmentCard();', SETUP)
        self.assertNotIn('[MenuItem(', PANEL)

    def test_stale_control_plane_does_not_claim_ready(self):
        self.assertIn('ControlPlaneVersionState() == "READY"', SETUP)
        self.assertIn('return "NEWER VERSION";', SETUP)
        self.assertIn('return "STALE";', SETUP)
        self.assertIn('ControlPlanePathResolver.HasOverride', SETUP)
        self.assertIn('"VERSION UNKNOWN"', SETUP)
        self.assertIn('GetManagedControlPlaneVersion', SETUP)
        self.assertIn('更新 / 修復', SETUP)
        self.assertIn('ControlPlaneBootstrap.Start', SETUP)
        self.assertIn('Environment.SetEnvironmentVariable(', SETUP)
        self.assertIn('!ControlPlanePathResolver.HasOverride', SETUP)

    def test_explicit_trusted_fixture_selection(self):
        for fixture in ('canonical-full', 'minimal-6000.3', 'minimal-6000.6',
                        'builtin-smoke', 'urp-smoke', 'hdrp-smoke'):
            self.assertIn('"' + fixture + '"', PANEL)
        self.assertIn('EditorUtility.DisplayDialog("Unity検証を実行"', PANEL)
        self.assertIn('s_licenseConfirmed', PANEL)
        self.assertIn('s_graphicsConfirmed', PANEL)
        self.assertIn('ci", "scripts", "run-unity-tests.ps1"', PANEL)
        source = (EDITOR / "VerificationFixtureSource.cs").read_text(encoding="utf-8")
        self.assertIn("p9-source-manifest.json", source)
        self.assertIn("TryGetVerifiedSource", PANEL)
        self.assertIn("UPM同梱", PANEL)
        self.assertNotIn("Hub checkout", PANEL)
        self.assertNotIn("OpenFolderPanel", PANEL)
        self.assertNotIn("HubRootPreferenceKey", PANEL)
        self.assertIn('UNITY_LICENSE_READY', PANEL)
        self.assertIn('UNITY_GRAPHICS_READY', PANEL)
        self.assertNotIn('unity-agent setup apply', PANEL)
        self.assertNotIn('ProcessStartInfo { FileName = "unity-agent"', PANEL)

    def test_evidence_rejects_unmeasured_success(self):
        self.assertIn('process.ExitCode == 0', PANEL)
        self.assertIn('evidence.status == "PASS"', PANEL)
        self.assertIn('evidence.observation == "observed"', PANEL)
        self.assertIn('process.ExitCode == 2', PANEL)
        self.assertIn('evidence.status == "BLOCKED_NOT_RUN"', PANEL)
        self.assertIn('evidence.observation == "not_observed"', PANEL)
        self.assertIn('Evidenceが生成されていません', PANEL)
        self.assertIn('Guid.NewGuid()', PANEL)
        self.assertIn('EditorUtility.RevealInFinder', PANEL)

    def test_unity_meta_guid_is_present_and_unique(self):
        meta = EDITOR / "SetupVerificationPanel.cs.meta"
        self.assertTrue(meta.is_file())
        match = re.search(r"(?m)^guid: ([a-f0-9]{32})$", meta.read_text(encoding="utf-8"))
        self.assertIsNotNone(match)
        guids = []
        for path in EDITOR.rglob("*.meta"):
            m = re.search(r"(?m)^guid: ([a-f0-9]{32})$", path.read_text(encoding="utf-8"))
            if m:
                guids.append(m.group(1))
        self.assertEqual(guids.count(match.group(1)), 1)

    def test_full_e2e_not_misreported(self):
        self.assertIn("Full E2E", PANEL)
        self.assertIn("別Gate", PANEL)


if __name__ == "__main__":
    unittest.main()
