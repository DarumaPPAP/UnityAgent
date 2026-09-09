"""Compatibility import for the named Local lexical MVP backend."""

from RAG.Retrieval.lexical_retriever import (
    LexicalScoringWeights,
    LocalLexicalBackend,
    matches_hard_filters,
    rank_candidates,
    score_candidate,
)

__all__ = [
    "LexicalScoringWeights",
    "LocalLexicalBackend",
    "matches_hard_filters",
    "rank_candidates",
    "score_candidate",
]
