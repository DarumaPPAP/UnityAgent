"""UnityAgent SetupからのHub管理キャッシュ取得・実行安全契約。"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "Packages/com.darumappap.unity-agent"
EDITOR = PKG / "Editor"
LOCK = ROOT / "src/unityagent/runtime/distribution/subagent-sources.lock.json"
MIRROR = EDITOR / "Verification~/subagent-sources.lock.json"


class EditorManagedHubVerificationTests(unittest.TestCase):
    def test_single_pinned_source(self):
        source = json.loads(LOCK.read_text(encoding="utf-8"))
        mirror = json.loads(MIRROR.read_text(encoding="utf-8"))
        self.assertEqual(source, mirror)
        self.assertEqual(source["hub"]["repository"], "DarumaPPAP/UnitySubAgentHub")
        self.assertRegex(source["hub"]["commit"], "^[0-9a-f]{40}$")

    def test_no_manual_checkout_ui(self):
        panel = (EDITOR / "SetupVerificationPanel.cs").read_text(encoding="utf-8")
        self.assertNotIn("s_hubRoot", panel)
        self.assertNotIn("OpenFolderPanel", panel)
        self.assertNotIn("HubRootPreferenceKey", panel)
        self.assertIn("検証環境を取得・更新", panel)
        self.assertIn("TryGetVerifiedCache", panel)
        self.assertIn("s_sourceReady", panel)

    def test_owned_cache_verified_before_use(self):
        source = (EDITOR / "VerificationHubSource.cs").read_text(encoding="utf-8")
        for word in ('GitRemote', 'rev-parse FETCH_HEAD', 'rev-parse HEAD',
                     'status --porcelain', 'Directory.Move', 'VerificationHub',
                     'Source Lock', 'TryGetVerifiedCache', 'GitRemote'):
            self.assertIn(word, source)
        self.assertNotIn("shell.exe", source)
        self.assertIn('RedirectStandardError = true', source)
        self.assertIn('"ci/scripts/run-unity-tests.ps1"', source)

    def test_meta_guid_present(self):
        meta = EDITOR / "VerificationHubSource.cs.meta"
        self.assertRegex(meta.read_text(encoding="utf-8"), r"(?m:^guid: [0-9a-f]{32}$)")


if __name__ == "__main__":
    unittest.main()
