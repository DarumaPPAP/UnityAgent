"""Small deterministic query classifier used for trace metadata and ranking hints."""

from __future__ import annotations

from typing import Any

from RAG.Query.normalize_query import NormalizedQuery, normalize_query


SYMPTOM_TOKENS = {
    "fail", "failure", "failed", "error", "broken", "missing", "crash", "spike",
    "失敗", "エラー", "壊れ", "不足", "ちらつき", "重い",
}
CONCEPT_TOKENS = {
    "how", "what", "difference", "design", "architecture", "compare", "方法", "違い", "設計",
}


def classify_query(query: str | NormalizedQuery) -> dict[str, Any]:
    normalized = query if isinstance(query, NormalizedQuery) else normalize_query(query)
    token_set = set(normalized.tokens)
    if len(normalized.technical_tokens) >= 2:
        kind = "technical_identifier_heavy"
    elif token_set & SYMPTOM_TOKENS:
        kind = "symptom"
    elif token_set & CONCEPT_TOKENS:
        kind = "conceptual"
    else:
        kind = "mixed"
    return {
        "kind": kind,
        "query_hash": normalized.query_hash,
        "technical_token_count": len(normalized.technical_tokens),
        "token_count": len(normalized.tokens),
    }
