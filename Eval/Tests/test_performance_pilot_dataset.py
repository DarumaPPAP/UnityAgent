from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


class PerformancePilotDatasetTests(unittest.TestCase):
    def test_dataset_is_ready_for_three_arm_run_without_promotion_claim(self) -> None:
        dataset = yaml.safe_load((ROOT / "Eval/Datasets/Specialists/performance-pilot.yaml").read_text(encoding="utf-8"))
        self.assertEqual(dataset["specialist_candidate"], "performance_subagent")
        self.assertEqual(dataset["status"], "pending_live_evaluation")
        self.assertEqual(dataset["promotion_decision"], "requires_human_review")
        self.assertEqual(set(dataset["comparison_arms"]), {"A", "B", "C"})
        self.assertEqual(len(dataset["cases"]), 6)
        self.assertTrue(all(case["expected_route"] == "performance-experiment" for case in dataset["cases"]))
        self.assertEqual(len({case["id"] for case in dataset["cases"]}), 6)
        self.assertIn("measurement_validity_handling", dataset["required_metrics"])


if __name__ == "__main__":
    unittest.main()
