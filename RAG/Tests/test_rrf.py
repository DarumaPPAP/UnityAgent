import unittest

from RAG.Ranking.rrf import reciprocal_rank_fusion
from RAG.Tests.test_ranking import item


class RrfTests(unittest.TestCase):
    def test_candidate_present_in_both_lists_wins(self):
        a, b = item("a"), item("b")
        result = reciprocal_rank_fusion({"lexical": [a, b], "semantic": [b, a]}, k=60)
        self.assertEqual(result[0].candidate_id, "a")
        self.assertEqual(result[1].candidate_id, "b")


if __name__ == "__main__":
    unittest.main()
