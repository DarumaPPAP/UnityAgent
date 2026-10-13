"""Unity Editorの短いclass名と既存GUID/Public identityの不変条件。"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "Packages/com.darumappap.unity-agent/Editor"
EDITOR_ASSEMBLY = "DarumaPPAP.UnityAgent.Editor"

# P0/P10以前から存在する .meta GUID。クラス・ファイルを改名しても変えない。
EXPECTED_GUIDS = {
    "CodexPathResolver": "7fd23cc03ccf4d14b23280ca9b76ef14",
    "ControlPlaneBootstrap": "7b4d37f735ba41c1959ae3e95d58bf7f",
    "ControlPlaneClient": "e288a608e6704ccaaa7564eb3a4d72eb",
    "ControlPlanePathResolver": "2a5c6bc4d51f48b8b7f18c0349ab5fa8",
    "FullE2EBridge": "46f6bac3e15b43388e53b81564224bbc",
    "SetupVerificationPanel": "7a4c2f66bb854726a4f0c35d7862e9db",
    "SetupWindow": "d565f335798d44a794dd5568624e5935",
}

OLD_TYPES = tuple("UnityAgent" + name for name in EXPECTED_GUIDS)


class EditorClassNamingTests(unittest.TestCase):
    def test_class_and_file_names_match_without_redundant_prefix(self):
        for name in EXPECTED_GUIDS:
            with self.subTest(name=name):
                path = EDITOR / (name + ".cs")
                self.assertTrue(path.is_file())
                self.assertFalse((EDITOR / ("UnityAgent" + name + ".cs")).exists())
                source = path.read_text(encoding="utf-8")
                self.assertIn("namespace " + EDITOR_ASSEMBLY, source)
                self.assertRegex(source, rf"\bclass\s+{name}\b")
                self.assertNotRegex(source, r"\bclass\s+UnityAgent")

    def test_meta_guids_survive_rename(self):
        for name, guid in EXPECTED_GUIDS.items():
            with self.subTest(name=name):
                path = EDITOR / (name + ".cs.meta")
                self.assertTrue(path.is_file())
                meta = path.read_text(encoding="utf-8")
                self.assertRegex(meta, rf"(?m:^guid:\s*{guid}$)")
                self.assertFalse((EDITOR / ("UnityAgent" + name + ".cs.meta")).exists())

    def test_ui_and_upm_assembly_identity_unchanged(self):
        asmdef = (EDITOR / (EDITOR_ASSEMBLY + ".asmdef")).read_text(encoding="utf-8")
        self.assertIn('"name": "' + EDITOR_ASSEMBLY + '"', asmdef)
        setup = (EDITOR / "SetupWindow.cs").read_text(encoding="utf-8")
        self.assertIn('[MenuItem("UnityAgent/Setup")]', setup)
        bridge = (EDITOR / "FullE2EBridge.cs").read_text(encoding="utf-8")
        self.assertIn('[InitializeOnLoad]', bridge)

    def test_no_stale_class_or_source_path_references(self):
        active = (
            ".github/workflows/validate-agent-contracts.yml",
            ".github/workflows/windows-bootstrap-smoke.yml",
            ".github/workflows/release-tag.yml",
            "tools/layer_boundary_validator/validate_layer_boundaries.py",
            "tests/packaging/test_setup_editor_verification_contract.py",
        )
        paths = sorted(EDITOR.glob("*.cs")) + [ROOT / name for name in active]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for old in OLD_TYPES:
                with self.subTest(path=path.name, old=old):
                    self.assertNotRegex(text, rf"\b{old}\b")


if __name__ == "__main__":
    unittest.main()
