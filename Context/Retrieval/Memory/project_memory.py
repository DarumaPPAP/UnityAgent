"""Compatibility wrapper for the pre-RAG Memory projection API.

Persistence remains the durable owner. New retrieval and candidate normalization
live in ``RAG.Adapters.memory``; this module only preserves the historical Context
projection shape for existing callers during the staged migration.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from Persistence.Store.atomic_store import PersistenceError
from RAG.Adapters.memory.adapter import MemoryAdapter
from RAG.Contracts.models import RetrievalFilters, RetrievalRequest, deterministic_id
from RAG.Query.normalize_query import normalize_query
from RAG.Retrieval.local_lexical_backend import LocalLexicalBackend


def retrieve_projections(
    *,
    store_root,
    query: str,
    execution_profile: str,
    selected_at: str,
    repository: str | None = None,
    unity_version: str | None = None,
    platform: str | None = None,
    max_items: int = 8,
    max_chars: int = 6000,
) -> dict[str, Any]:
    """Return the old bounded projection shape through the RAG read path."""

    if not 1 <= max_items <= 20:
        raise ValueError("max_items must be 1..20")
    if not 256 <= max_chars <= 12_000:
        raise ValueError("max_chars must be 256..12000")
    normalized = normalize_query(query)
    filters = RetrievalFilters(
        repository=repository,
        unity_version=unity_version,
        platforms=(platform,) if platform else (),
    )
    request = RetrievalRequest(
        request_id=deterministic_id("memory-projection", normalized.query_hash, selected_at),
        raw_query=query,
        normalized_query=normalized.normalized,
        route_id="memory-projection-compatibility",
        execution_profile=execution_profile,
        filters=filters,
        top_k=max_items,
        candidate_k=max(24, max_items),
        max_chars=max_chars,
        sources=("project_memory",),
        query_tokens=normalized.tokens,
        technical_tokens=normalized.technical_tokens,
    )
    loaded = MemoryAdapter(store_root, execution_profile).load()
    if loaded.diagnostics:
        diagnostic = loaded.diagnostics[0]
        raise PersistenceError(
            "memory_source_unavailable",
            str(diagnostic.get("message") or diagnostic.get("code") or "Memory source unavailable"),
        )
    ranked = LocalLexicalBackend(loaded.candidates).retrieve(request)

    items: list[dict[str, Any]] = []
    characters = 0
    truncated = False
    for candidate in ranked:
        if len(items) >= max_items:
            truncated = True
            break
        evidence_refs = list(candidate.provenance.evidence_ids)
        if candidate.evidence_id and candidate.evidence_id not in evidence_refs:
            evidence_refs.insert(0, candidate.evidence_id)
        projection = {
            "schema_version": "1.0",
            "projection_id": "memory-projection-" + hashlib.sha256(
                f"{candidate.document_id}:{selected_at}".encode()
            ).hexdigest()[:16],
            "memory_id": candidate.document_id,
            "source_evidence_refs": evidence_refs,
            "projection_ref": candidate.source_ref,
            "selected_at": selected_at,
        }
        item = {
            "projection": projection,
            "statement": candidate.statement,
            "confidence": candidate.confidence,
            "applicability": list(candidate.metadata.get("domains") or []),
            "limits": list(candidate.metadata.get("limits") or []),
            "score": round(candidate.lexical_score, 3),
        }
        size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
        if items and characters + size > max_chars:
            truncated = True
            break
        if not items and size > max_chars:
            item["statement"] = item["statement"][: max(64, max_chars // 2)]
            size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
            truncated = True
        items.append(item)
        characters += size
    return {
        "query": query,
        "execution_profile": execution_profile,
        "items": items,
        "item_count": len(items),
        "characters": characters,
        "truncated": truncated,
        "raw_content_included": False,
        "durable_memory_owner": "Persistence/Memory",
    }
