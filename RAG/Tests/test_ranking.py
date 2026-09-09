import unittest
from pathlib import Path

from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate, RetrievalRequest
from RAG.Ranking.reranker import TechnicalReranker
from RAG.Ranking.config import load_ranking_config
from RAG.Ranking.rrf import RRFConfig, reciprocal_rank_fusion, weighted_reciprocal_rank_fusion


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

    def test_weighted_rrf_uses_versioned_weights(self):
        a, b = item("a"), item("b")
        config = RRFConfig(k=1, weights={"lexical": 2.0, "semantic": 0.1}, revision="eval-v1")
        fused = weighted_reciprocal_rank_fusion(
            {"lexical": [a], "semantic": [b]}, config=config
        )
        self.assertEqual(fused[0].candidate_id, "a")
        self.assertEqual(config.to_dict()["revision"], "eval-v1")

    def test_technical_reranker_only_reorders_candidates(self):
        first, second = item("first"), item("second")
        first.summary = "unrelated explanation"
        second.summary = "RenderGraph raster pass"
        request = RetrievalRequest(
            request_id="req-rerank",
            raw_query="RenderGraph raster pass",
            normalized_query="rendergraph raster pass",
            route_id="test",
            execution_profile="generic_planning",
            top_k=2,
            candidate_k=2,
            max_chars=256,
            query_tokens=("rendergraph", "raster", "pass"),
            technical_tokens=("RenderGraph",),
        )
        ranked = TechnicalReranker().rerank(request, [first, second])
        self.assertEqual([candidate.candidate_id for candidate in ranked], ["second", "first"])
        self.assertTrue(all(candidate.source_ref.startswith("fixture://") for candidate in ranked))

    def test_mixed_sources_keep_source_qualified_identity(self):
        fixture = item("shared")
        memory = item("shared")
        memory.source_kind = "project_memory"
        memory.source_ref = "persistence://memory/shared"
        memory.provenance = CandidateProvenance(
            source_kind="project_memory",
            source_ref="persistence://memory/shared",
            document_id="shared",
        )
        fused = reciprocal_rank_fusion({"lexical": [fixture], "semantic": [memory]})
        self.assertEqual(len(fused), 2)
        self.assertEqual({candidate.source_kind for candidate in fused}, {"fixture", "project_memory"})

    def test_repository_ranking_config_is_versioned(self):
        root = Path(__file__).resolve().parents[2]
        config, public = load_ranking_config(root / "RAG/Ranking/ranking-config.yaml")
        self.assertEqual(public["algorithm"], "weighted_rrf")
        self.assertEqual(config.revision, "rrf-v2")
        self.assertEqual(config.weights["lexical"], 1.35)


if __name__ == "__main__":
    unittest.main()
