"""Bounded graph-expansion seam reserved for a later retrieval phase."""

from __future__ import annotations

from collections.abc import Iterable

from RAG.Contracts.models import RetrievalCandidate


def expand_candidates(candidates: Iterable[RetrievalCandidate], *, max_hops: int = 0) -> list[RetrievalCandidate]:
    """Return the seed candidates until a graph source is explicitly configured."""

    if max_hops < 0:
        raise ValueError("max_hops must be non-negative")
    # No graph is implicitly inferred from retrieved text; relation provenance is
    # required before a later implementation can add nodes.
    return list(candidates)


__all__ = ["expand_candidates"]
