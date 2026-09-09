"""Build a bounded Grounding Bundle from ranked candidates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from RAG.Contracts.models import (
    GroundingBundle,
    RetrievalCandidate,
    RetrievalRequest,
    deterministic_id,
)
from RAG.Grounding.provenance_validator import ProvenanceError, validate_provenance


def _bounded_statement(text: str, remaining: int) -> str:
    if remaining <= 0:
        return ""
    value = str(text).strip()
    if len(value) <= remaining:
        return value
    if remaining <= 1:
        return value[:remaining]
    return value[: remaining - 1].rstrip() + "…"


def build_grounding_bundle(
    request: RetrievalRequest,
    candidates: Iterable[RetrievalCandidate],
    *,
    source_failures: Iterable[Mapping[str, Any]] = (),
    max_items: int | None = None,
    max_chars: int | None = None,
) -> GroundingBundle:
    """Keep only candidates with auditable provenance and bounded statements."""

    item_limit = max_items if max_items is not None else request.top_k
    char_limit = max_chars if max_chars is not None else request.max_chars
    if not 1 <= int(item_limit) <= 20:
        raise ValueError("grounding max_items must be 1..20")
    if not 256 <= int(char_limit) <= 100_000:
        raise ValueError("grounding max_chars must be 256..100000")

    candidate_list = list(candidates)
    failures = [dict(item) for item in source_failures]
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    blocked_by_original = False
    remaining = int(char_limit)
    for candidate in candidate_list[: int(item_limit)]:
        try:
            provenance = validate_provenance(candidate.provenance)
        except ProvenanceError as exc:
            skipped.append({"candidate_id": candidate.candidate_id, "code": exc.code, "reason": str(exc)})
            blocked_by_original = blocked_by_original or exc.code == "blocked_original_unreadable"
            continue
        statement = _bounded_statement(candidate.statement, remaining)
        if not statement:
            break
        item = {
            "candidate_id": candidate.candidate_id,
            "source_kind": candidate.source_kind,
            "statement": statement,
            "provenance": provenance.to_dict(),
            "confidence": candidate.confidence,
            "review_status": candidate.review_status,
            "scores": {
                "lexical": round(float(candidate.lexical_score), 6),
                "semantic": round(float(candidate.semantic_score), 6),
                "fusion": round(float(candidate.fusion_score), 6),
                "rerank": None if candidate.rerank_score is None else round(float(candidate.rerank_score), 6),
            },
        }
        items.append(item)
        remaining -= len(statement)
        if remaining <= 0:
            break

    if not items:
        status = "blocked" if failures or blocked_by_original else "no_answer"
    elif failures or skipped:
        status = "partial"
    else:
        status = "grounded"
    diagnostics = {
        "candidate_count": len(candidate_list),
        "grounded_count": len(items),
        "skipped_candidates": skipped,
        "source_failures": failures,
        "bounded": True,
        "max_items": int(item_limit),
        "max_chars": int(char_limit),
    }
    bundle_id = deterministic_id(
        "gb", request.request_id, request.normalized_query, *(item["candidate_id"] for item in items)
    )
    return GroundingBundle(
        grounding_bundle_id=bundle_id,
        request_id=request.request_id,
        items=tuple(items),
        diagnostics=diagnostics,
        status=status,
    )
