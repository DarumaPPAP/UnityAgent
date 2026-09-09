"""Optional reranking seam; the MVP deliberately has no opaque model dependency."""

from __future__ import annotations

from typing import Protocol

from RAG.Contracts.models import RetrievalCandidate, RetrievalRequest


class Reranker(Protocol):
    revision: str

    def rerank(
        self, request: RetrievalRequest, candidates: list[RetrievalCandidate]
    ) -> list[RetrievalCandidate]: ...


class NoopReranker:
    revision = "none-v1"

    def rerank(self, request: RetrievalRequest, candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        return candidates


__all__ = ["NoopReranker", "Reranker"]
