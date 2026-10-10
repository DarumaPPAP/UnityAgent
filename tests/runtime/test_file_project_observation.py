"""Project設定の実ファイル読取。Editor実行を主張しない。"""
import tempfile
import unittest
from pathlib import Path

from unityagent.runtime.tooling.providers.file.file_provider import FileProvider


class FileProjectObservationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ("Assets", "Packages", "ProjectSettings"):
            (self.root / name).mkdir()
        (self.root / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.15f1\n", encoding="utf-8")
        self.request = {"schema_version": "1.0", "capability": "project.inspect", "project_root": str(self.root), "operation_kind": "read", "required_evidence": ["project_fact"], "mutation_scope": None, "approval_ref": None, "preferred_surface": "project"}

    def settings(self, pipeline="{fileID: 0}", override="{fileID: 0}"):
        (self.root / "ProjectSettings/GraphicsSettings.asset").write_text(f"%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!30 &1\nGraphicsSettings:\n  m_CustomRenderPipeline: {pipeline}\n", encoding="utf-8")
        (self.root / "ProjectSettings/QualitySettings.asset").write_text(f"QualitySettings:\n  m_QualitySettings:\n  - name: Low\n    customRenderPipeline: {override}\n", encoding="utf-8")

    def inspect(self):
        return FileProvider(self.root).inspect_project(self.request, policy_allowed=True)

    def test_builtin_requires_explicit_null_graphics_and_quality_settings(self):
        self.settings()
        result = self.inspect()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["render_pipeline"], "builtin")
        self.assertEqual(result["observation_scope"], "serialized_project_configuration")
        self.assertEqual(result["runtime_evaluation"], "NOT_EVALUATED_RUNTIME")
        self.assertEqual(len(result["sources"]), 3)
        (self.root / "ProjectSettings/QualitySettings.asset").unlink()
        self.assertEqual(self.inspect()["render_pipeline"], "unknown")

    def test_urp_asset_is_identified_by_resolved_script_guid_not_package_presence(self):
        guid, script = "a" * 32, "b" * 32
        pipeline = f"{{fileID: 11400000, guid: {guid}, type: 2}}"
        self.settings(pipeline)
        asset = self.root / "Assets/Pipeline.asset"
        asset.write_text(f"MonoBehaviour:\n  m_Script: {{fileID: 11500000, guid: {script}, type: 3}}\n", encoding="utf-8")
        asset.with_suffix(".asset.meta").write_text(f"guid: {guid}\n", encoding="utf-8")
        package = self.root / "Packages/com.unity.render-pipelines.universal/Runtime/Data"
        package.mkdir(parents=True)
        (package / "UniversalRenderPipelineAsset.cs.meta").write_text(f"guid: {script}\n", encoding="utf-8")
        self.assertEqual(self.inspect()["render_pipeline"], "urp")
        self.settings()
        self.assertEqual(self.inspect()["render_pipeline"], "builtin")
        self.settings(pipeline, "{fileID: 11400000, guid: " + "c" * 32 + ", type: 2}")
        self.assertEqual(self.inspect()["render_pipeline"], "unknown")

    def test_duplicate_yaml_or_guid_does_not_guess(self):
        self.settings()
        (self.root / "ProjectSettings/GraphicsSettings.asset").write_text("GraphicsSettings:\n  m_CustomRenderPipeline: {fileID: 0}\n  m_CustomRenderPipeline: {fileID: 0}\n", encoding="utf-8")
        self.assertEqual(self.inspect()["render_pipeline"], "unknown")

    def test_project_and_policy_boundaries_are_kept(self):
        provider = FileProvider(self.root)
        self.assertEqual(provider.inspect_project(self.request, policy_allowed=False)["failure_class"], "blocked_by_policy")
        self.assertEqual(provider.inspect_project({**self.request, "project_root": str(self.root / "Assets")}, policy_allowed=True)["failure_class"], "scope_violation")


if __name__ == "__main__":
    unittest.main()
