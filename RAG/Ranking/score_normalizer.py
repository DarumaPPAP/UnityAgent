"""Small, deterministic score normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable

from RAG.Contracts.models import RetrievalCandidate


def normalize_scores(
    candidates: Iterable[RetrievalCandidate],
    *,
    score_attribute: str = "lexical_score",
) -> list[RetrievalCandidate]:
    """Normalize one score field to [0, 1] while preserving stable ordering."""

    values = list(candidates)
    if not values:
        return []
    scores = [float(getattr(item, score_attribute, 0.0) or 0.0) for item in values]
    low, high = min(scores), max(scores)
    if high == low:
        normalized = [1.0 if high > 0 else 0.0 for _ in scores]
    else:
        normalized = [(value - low) / (high - low) for value in scores]
    for candidate, score in zip(values, normalized):
        if score_attribute == "lexical_score":
            candidate.lexical_score = score
        elif score_attribute == "semantic_score":
            candidate.semantic_score = score
        elif score_attribute == "fusion_score":
            candidate.fusion_score = score
        elif score_attribute == "rerank_score":
            candidate.rerank_score = score
        else:
            raise ValueError(f"unsupported score attribute: {score_attribute}")
    return values
