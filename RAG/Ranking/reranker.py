"""Bounded reranking seam with a deterministic technical baseline."""

from __future__ import annotations

import re
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


class TechnicalReranker:
    """Deterministic candidate-only reranker for technical identifiers."""

    revision = "technical-reranker-v1"
    _TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_+.:-]*|[^\W_]+", re.UNICODE)

    def rerank(self, request: RetrievalRequest, candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
        query_tokens = {str(value).casefold() for value in request.query_tokens if str(value).strip()}
        technical_tokens = {str(value).casefold() for value in request.technical_tokens if str(value).strip()}
        ranked: list[tuple[float, RetrievalCandidate]] = []
        for candidate in candidates:
            text = candidate.searchable_text().casefold()
            tokens = {value.casefold() for value in self._TOKEN_RE.findall(text)}
            exact = len(technical_tokens & tokens)
            overlap = len(query_tokens & tokens)
            review = 0.15 if str(candidate.review_status or "").casefold() in {"reviewed", "approved"} else 0.0
            score = (
                (2.0 * exact)
                + (0.35 * overlap)
                + (0.2 * float(candidate.fusion_score or 0.0))
                + (0.1 * float(candidate.semantic_score or 0.0))
                + review
            )
            candidate.rerank_score = score
            ranked.append((score, candidate))
        ranked.sort(key=lambda item: (-item[0], item[1].candidate_id, item[1].source_ref))
        return [candidate for _, candidate in ranked]


__all__ = ["NoopReranker", "Reranker", "TechnicalReranker"]
