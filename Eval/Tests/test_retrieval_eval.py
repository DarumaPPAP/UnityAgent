import unittest

from Eval.Retrieval.run_retrieval_eval import DEFAULT_BASELINE, run


class RetrievalEvaluationTests(unittest.TestCase):
    def test_golden_retrieval_meets_initial_acceptance_thresholds(self):
        report = run(baseline_path=DEFAULT_BASELINE)
        self.assertEqual(report["decision"], "PASS")
        self.assertGreaterEqual(report["metrics"]["recall_at_5"], 0.80)
        self.assertGreaterEqual(report["metrics"]["recall_at_10"], 0.90)
        self.assertGreaterEqual(report["metrics"]["mrr"], 0.70)
        self.assertEqual(report["metrics"]["provenance_completeness"], 1.0)
        self.assertLessEqual(report["metrics"]["no_answer_false_positive_rate"], 0.10)


if __name__ == "__main__":
    unittest.main()
