"""Reciprocal Rank Fusion with deterministic tie handling."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from RAG.Contracts.models import RetrievalCandidate


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Iterable[RetrievalCandidate]] | Sequence[Iterable[RetrievalCandidate]],
    *,
    weights: Mapping[str, float] | None = None,
    k: int = 60,
    limit: int | None = None,
) -> list[RetrievalCandidate]:
    """Fuse ranked lists without losing the original candidate objects.

    Candidate identity is the source-qualified ``source_ref`` when available. This
    prevents identical document ids in two sources from being collapsed together.
    """

    if k <= 0:
        raise ValueError("RRF k must be positive")
    lists = list(ranked_lists.items()) if isinstance(ranked_lists, Mapping) else [
        (str(index), values) for index, values in enumerate(ranked_lists)
    ]
    by_key: dict[str, RetrievalCandidate] = {}
    fused: dict[str, float] = {}
    for list_name, ranked in lists:
        weight = float((weights or {}).get(str(list_name), 1.0))
        for rank, candidate in enumerate(ranked, start=1):
            key = candidate.source_ref or candidate.candidate_id
            by_key.setdefault(key, candidate)
            fused[key] = fused.get(key, 0.0) + weight / (k + rank)
    for key, candidate in by_key.items():
        candidate.fusion_score = fused[key]
    result = sorted(
        by_key.values(),
        key=lambda item: (-item.fusion_score, item.candidate_id, item.source_ref),
    )
    return result if limit is None else result[: max(0, int(limit))]
