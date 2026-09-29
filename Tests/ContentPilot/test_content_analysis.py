"""Content Pilotは入力観測の欠落を推測で埋めず、Applyを実行しない。"""
import unittest

from Tools.ContentPilot.content_analysis import analyze_texture, analyze_audio, analyze_addressables


class ContentAnalysisTests(unittest.TestCase):
    def test_texture_requires_project_decision_and_bounded_normal_samples(self):
        texture = {"asset_path": "Assets/Normal.png", "usage": "normal", "width": 1024, "height": 1024, "has_alpha": False, "current_format": "BC5", "sampled_normals": [[0.5, 0.5, 1.0]] * 8, "sample_strategy": "uniform_uv_grid"}
        decision = {"normal_flat_distance": 0.05, "normal_flat_min_samples": 8, "normal_flat_confidence": 0.9, "low_normal_format": "BC1", "high_normal_format": "BC5"}
        result = analyze_texture(texture, project_decision=decision)
        self.assertEqual(result["classification"], "low_normal_candidate")
        self.assertEqual(result["proposed_format"], "BC1")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual((result["flat_fraction"], result["sample_strategy"], result["sample_count"]), (1.0, "uniform_uv_grid", 8))
        self.assertTrue(result["known_limitations"])
        self.assertEqual(result["classification_criteria"], {"flat_distance": 0.05, "minimum_samples": 8, "flat_fraction_threshold": 0.9, "observed_samples": 8})
        self.assertEqual(result["proposed_changes"], [{"field": "format", "before": "BC5", "after": "BC1"}])
        self.assertTrue(result["approval_required"])
        self.assertIsNone(result["proposed_max_size"])
        self.assertFalse(result["applied"])
        self.assertEqual(analyze_texture({**texture, "sampled_normals": []}, project_decision=decision)["classification"], "unobserved")
        self.assertEqual(analyze_texture({**texture, "sample_strategy": None}, project_decision=decision)["classification"], "unobserved")
        self.assertEqual(analyze_texture(texture, project_decision={})["proposed_format"], None)
        self.assertEqual(analyze_texture({**texture, "current_format": None}, project_decision=decision)["status"], "candidate_only")

    def test_audio_analyze_is_separate_from_change_plan(self):
        audio = {"asset_path": "Assets/Voice.wav", "original_size_bytes": 123456, "load_type": "DecompressOnLoad", "compression_format": "PCM", "quality": 1.0, "preload": True, "load_in_background": False, "platform_overrides": {"Standalone": {"load_type": "Streaming", "compression_format": "Vorbis", "quality": 0.6}}}
        observed = analyze_audio(audio, project_decision=None)
        self.assertEqual(observed["status"], "observed")
        self.assertEqual(observed["proposed_changes"], [])
        planned = analyze_audio(audio, project_decision={"load_type": "Streaming", "compression_format": "Vorbis", "quality": 0.7, "preload": False, "load_in_background": True})
        self.assertEqual(planned["status"], "change_plan")
        self.assertEqual({item["field"] for item in planned["proposed_changes"]}, {"load_type", "compression_format", "quality", "preload", "load_in_background"})
        self.assertTrue(planned["approval_required"])
        self.assertFalse(planned["applied"])
        self.assertEqual(planned["observed"]["platform_overrides"], audio["platform_overrides"])

    def test_addressables_analyze_plan_and_apply_boundary(self):
        observation = {"asset_path": "Assets/A.prefab", "package_installed": True, "settings_present": True, "current_group": "Default", "current_address": "A", "groups": ["Default", "Remote"], "revision": "sha256:" + "a" * 64}
        analysis = analyze_addressables(observation)
        self.assertEqual(analysis["status"], "observed")
        self.assertEqual(analysis["proposed_changes"], [])
        plan = analyze_addressables(observation, proposed_group="Remote", proposed_address="A/Remote")
        self.assertEqual(plan["status"], "change_plan")
        self.assertEqual(plan["expected_revision"], observation["revision"])
        self.assertTrue(plan["approval_required"])
        self.assertFalse(plan["applied"])
        self.assertEqual(analyze_addressables({**observation, "package_installed": False})["status"], "unsupported")
        self.assertEqual(analyze_addressables(observation, proposed_group="Missing", proposed_address="A")["status"], "unavailable")

    def test_same_observation_and_decision_repeat_without_mutation(self):
        texture = {"asset_path": "Assets/T.png", "usage": "color", "width": 256, "height": 256, "has_alpha": True, "current_format": "BC1"}
        audio = {"asset_path": "Assets/A.wav", "original_size_bytes": 100, "load_type": "DecompressOnLoad", "compression_format": "PCM", "quality": 1.0, "preload": True, "load_in_background": False, "platform_overrides": {}}
        addressables = {"asset_path": "Assets/A.prefab", "package_installed": True, "settings_present": True, "current_group": "Default", "current_address": "A", "groups": ["Default", "Remote"], "revision": "sha256:" + "a" * 64}
        for operation in (lambda: analyze_texture(texture, project_decision={"color_formats": {"with_alpha": "BC3"}}), lambda: analyze_audio(audio, project_decision={"load_type": "Streaming"}), lambda: analyze_addressables(addressables, proposed_group="Remote", proposed_address="A/Remote")):
            with self.subTest(operation=operation):
                self.assertEqual(operation(), operation())
        self.assertEqual(texture["current_format"], "BC1")
        self.assertEqual(audio["load_type"], "DecompressOnLoad")
        self.assertEqual(addressables["current_group"], "Default")


if __name__ == "__main__":
    unittest.main()
