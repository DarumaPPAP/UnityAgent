from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


class WorldCreatorPilotDatasetTests(unittest.TestCase):
    def test_dataset_has_three_arms_and_five_cases_without_promotion_claim(self) -> None:
        dataset = yaml.safe_load((ROOT / "Eval/Datasets/Specialists/world-creator-pilot.yaml").read_text(encoding="utf-8"))
        self.assertEqual(dataset["specialist_candidate"], "world_creator_subagent")
        self.assertEqual(dataset["status"], "pending_live_evaluation")
        self.assertEqual(dataset["promotion_decision"], "requires_human_review")
        self.assertEqual(set(dataset["comparison_arms"]), {"A", "B", "C"})
        self.assertEqual({case["id"] for case in dataset["cases"]}, {"dungeon", "boss_arena", "live_stage", "multi_zone_world", "existing_scene_expansion"})
        self.assertTrue(all(case["expected_route"] == "world-creation" for case in dataset["cases"]))
        self.assertIn("hidden_decision_count", dataset["required_metrics"])


if __name__ == "__main__":
    unittest.main()
