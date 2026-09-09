"""Deterministic, non-generative query rewrite for technical identifiers."""

from __future__ import annotations

from RAG.Query.normalize_query import NormalizedQuery, normalize_query


def rewrite_query(query: str | NormalizedQuery) -> NormalizedQuery:
    """Normalize separators while keeping the user's terms authoritative.

    The MVP intentionally does not invent synonyms or project metadata. Identifier
    splitting is already represented in ``NormalizedQuery.tokens``.
    """

    return query if isinstance(query, NormalizedQuery) else normalize_query(query)


__all__ = ["rewrite_query"]
