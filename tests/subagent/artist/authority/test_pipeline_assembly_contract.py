"""Pipeline 0.8 の CLI 属性 Assembly と Artist の import 契約を照合する静的 Gate。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[4]
EDITOR = ROOT / "subagent/artist_subagent/tools/editor"


class PipelineAssemblyTests(unittest.TestCase):
    def test_command_registration_references_attributes_assembly(self):
        assembly = json.loads((EDITOR / "Editor/Pipeline/UnityArtist.Pipeline.Editor.asmdef").read_text(encoding="utf-8"))
        self.assertIn("Unity.Pipeline.Attributes", assembly["references"])
        self.assertNotIn("Unity.Pipeline", assembly["references"])
        self.assertEqual(assembly["versionDefines"], [{"name": "com.unity.pipeline", "expression": "0.8.0-exp.1", "define": "UNITY_ARTIST_PIPELINE"}])

    def test_pipeline_remains_optional_and_minimum_is_visible(self):
        package = json.loads((EDITOR / "package.json").read_text(encoding="utf-8"))
        self.assertNotIn("com.unity.pipeline", package["dependencies"])
        self.assertIn("0.8.0-exp.1", package["description"])


if __name__ == "__main__":
    unittest.main()
