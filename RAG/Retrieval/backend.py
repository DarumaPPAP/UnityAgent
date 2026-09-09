"""Backend-independent retrieval protocol."""

from __future__ import annotations

from typing import Protocol

from RAG.Contracts.models import RetrievalCandidate, RetrievalRequest


class BackendUnavailableError(RuntimeError):
    """Raised when a configured backend cannot answer the request."""


class RetrievalBackend(Protocol):
    def capabilities(self) -> set[str]:
        """Return capability names without exposing provider-specific types."""

    def retrieve(self, request: RetrievalRequest) -> list[RetrievalCandidate]:
        """Return at most request.candidate_k ranked candidates."""
