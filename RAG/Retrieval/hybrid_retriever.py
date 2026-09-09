"""Optional hybrid retrieval composition behind the backend protocol."""

from __future__ import annotations

from RAG.Contracts.models import RetrievalCandidate, RetrievalRequest
from RAG.Ranking.rrf import reciprocal_rank_fusion


class HybridRetriever:
    """Fuse independently ranked lexical and semantic result sets with RRF."""

    revision = "hybrid-rrf-v1"

    def __init__(self, lexical, semantic) -> None:
        self.lexical = lexical
        self.semantic = semantic

    def capabilities(self) -> set[str]:
        return {"lexical", "dense", "hybrid", "filtering"}

    def retrieve(self, request: RetrievalRequest) -> list[RetrievalCandidate]:
        lexical = self.lexical.retrieve(request)
        semantic = self.semantic.retrieve(request)
        return reciprocal_rank_fusion(
            {"lexical": lexical, "semantic": semantic},
            limit=request.candidate_k,
        )


__all__ = ["HybridRetriever"]
