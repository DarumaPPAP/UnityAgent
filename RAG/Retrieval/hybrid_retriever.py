"""Optional hybrid retrieval composition behind the backend protocol."""

from __future__ import annotations

from RAG.Contracts.models import RetrievalCandidate, RetrievalRequest
from RAG.Ranking.reranker import NoopReranker, Reranker
from RAG.Ranking.rrf import RRFConfig, reciprocal_rank_fusion


class HybridRetriever:
    """Fuse independently ranked lexical and semantic result sets with RRF."""

    revision = "hybrid-rrf-v1"

    def __init__(self, lexical, semantic, *, rrf_config: RRFConfig | None = None, reranker: Reranker | None = None) -> None:
        self.lexical = lexical
        self.semantic = semantic
        self.rrf_config = rrf_config or RRFConfig(weights={"lexical": 1.0, "semantic": 1.0})
        self.reranker = reranker or NoopReranker()

    def capabilities(self) -> set[str]:
        capabilities = {"lexical", "dense", "hybrid", "filtering", "rrf", "weighted_rrf"}
        if not isinstance(self.reranker, NoopReranker):
            capabilities.add("rerank")
        return capabilities

    def retrieve(self, request: RetrievalRequest) -> list[RetrievalCandidate]:
        lexical = self.lexical.retrieve(request)
        semantic = self.semantic.retrieve(request)
        fused = reciprocal_rank_fusion(
            {"lexical": lexical, "semantic": semantic},
            config=self.rrf_config,
            limit=request.candidate_k,
        )
        return self.reranker.rerank(request, fused[: request.candidate_k])[: request.candidate_k]


__all__ = ["HybridRetriever"]
