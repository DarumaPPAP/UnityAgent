"""Compatibility import for the named Local lexical MVP backend."""

from RAG.Retrieval.lexical_retriever import (
    LexicalScoringWeights,
    LocalLexicalBackend,
    matches_hard_filters,
    rank_candidates,
    score_candidate,
)

LocalSearchIndexBackend = LocalLexicalBackend

__all__ = [
    "LexicalScoringWeights",
    "LocalLexicalBackend",
    "LocalSearchIndexBackend",
    "matches_hard_filters",
    "rank_candidates",
    "score_candidate",
]
