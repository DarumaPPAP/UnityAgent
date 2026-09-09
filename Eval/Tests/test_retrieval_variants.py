import unittest

from Eval.Retrieval.run_retrieval_variants import VARIANT_NAMES, run


class RetrievalVariantTests(unittest.TestCase):
    def test_all_offline_variants_are_comparable_and_hybrid_passes(self):
        report = run()
        self.assertEqual(report["overall_decision"], "PASS")
        self.assertEqual(tuple(report["variants"]), VARIANT_NAMES)
        self.assertEqual(report["variants"]["local_lexical"]["decision"], "PASS")
        self.assertEqual(report["variants"]["hybrid_weighted_rrf"]["decision"], "PASS")
        self.assertEqual(report["variants"]["hybrid_rerank"]["ranking_config"]["reranker"], "technical-reranker-v1")
        self.assertGreaterEqual(report["variants"]["hybrid_rerank"]["performance"]["p95_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
