import unittest

from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate
from RAG.Ranking.rrf import reciprocal_rank_fusion


def item(value: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        candidate_id=value,
        source_kind="fixture",
        source_ref=f"fixture://{value}",
        document_id=value,
        evidence_id=f"EV-{value}",
        heading="item",
        summary=value,
        content=value,
        metadata={},
        provenance=CandidateProvenance(source_kind="fixture", source_ref=f"fixture://{value}", document_id=value),
    )


class RankingTests(unittest.TestCase):
    def test_rrf_favors_agreement_and_is_deterministic(self):
        a, b, c = item("a"), item("b"), item("c")
        fused = reciprocal_rank_fusion({"lexical": [a, b], "semantic": [b, c]}, k=1)
        self.assertEqual(fused[0].candidate_id, "b")
        self.assertGreater(fused[0].fusion_score, fused[-1].fusion_score)


if __name__ == "__main__":
    unittest.main()
