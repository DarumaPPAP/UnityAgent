"""Deterministic local dense baseline used for offline hybrid evaluation."""

from __future__ import annotations

from collections.abc import Iterable
import math

from RAG.Adapters.qdrant.embeddings import DenseEmbedder, HashingDenseEmbedder
from RAG.Contracts.models import RetrievalCandidate, RetrievalRequest
from RAG.Retrieval.lexical_retriever import matches_hard_filters


class LocalDenseBackend:
    """Brute-force dense backend with an injectable approved embedder.

    The default hashing embedder is deterministic and dependency-free for CI.
    It provides the same backend contract as a remote semantic adapter; it is
    not claimed to be a production-quality semantic model.
    """

    revision = "local-dense-v1"

    def __init__(
        self,
        candidates: Iterable[RetrievalCandidate] = (),
        *,
        embedder: DenseEmbedder | None = None,
        min_score: float = 0.1,
    ) -> None:
        self._candidates = tuple(candidates)
        self.embedder = embedder or HashingDenseEmbedder()
        self.min_score = float(min_score)

    def capabilities(self) -> set[str]:
        return {"dense", "filtering"}

    def retrieve(self, request: RetrievalRequest) -> list[RetrievalCandidate]:
        query = self.embedder.embed_query(request.normalized_query)
        ranked: list[RetrievalCandidate] = []
        for candidate in self._candidates:
            if not matches_hard_filters(candidate, request.filters):
                continue
            vector = self.embedder.embed_document(candidate.searchable_text())
            score = self._cosine(query, vector)
            candidate.semantic_score = score
            candidate.lexical_score = 0.0
            candidate.fusion_score = 0.0
            candidate.rerank_score = None
            if score >= self.min_score:
                ranked.append(candidate)
        ranked.sort(key=lambda item: (-item.semantic_score, item.candidate_id, item.source_ref))
        return ranked[: request.candidate_k]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError("dense vector dimensions must match")
        numerator = sum(float(a) * float(b) for a, b in zip(left, right))
        left_norm = math.sqrt(sum(float(value) * float(value) for value in left))
        right_norm = math.sqrt(sum(float(value) * float(value) for value in right))
        return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


__all__ = ["LocalDenseBackend"]
