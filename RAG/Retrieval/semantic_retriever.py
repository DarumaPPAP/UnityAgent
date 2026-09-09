"""Optional dense retrieval protocol; no embedding dependency is required by MVP."""

from __future__ import annotations

from typing import Protocol

from RAG.Contracts.models import RetrievalCandidate, RetrievalRequest


class SemanticRetriever(Protocol):
    revision: str

    def retrieve(self, request: RetrievalRequest) -> list[RetrievalCandidate]: ...


__all__ = ["SemanticRetriever"]
