"""Translate RAG metadata filters to Qdrant payload filter JSON."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from RAG.Contracts.models import RetrievalFilters


def _condition(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, (tuple, list, set)):
        values = [str(item) for item in value if str(item).strip()]
        return {"key": key, "match": {"any": values}}
    return {"key": key, "match": {"value": str(value)}}


def build_qdrant_filter(filters: RetrievalFilters) -> dict[str, Any] | None:
    """Return Qdrant's ``must`` filter while preserving hard/explicit fields."""

    conditions: list[dict[str, Any]] = []
    scalar_fields = {
        "repository": "repository",
        "project_id": "project_id",
        "engine": "engine",
        "source_kind": "source_kind",
        "document_id": "document_id",
        "review_status": "review_status",
        "confidence": "confidence",
        "pipeline_version": "pipeline_version",
    }
    for attribute, payload_key in scalar_fields.items():
        value = getattr(filters, attribute)
        if value:
            conditions.append(_condition(payload_key, value))
    list_fields = {
        "platforms": "platforms",
        "domains": "domains",
        "topics": "topics",
        "tags": "tags",
    }
    for attribute, payload_key in list_fields.items():
        values = getattr(filters, attribute)
        if values:
            conditions.append(_condition(payload_key, values))
    if filters.unity_version:
        conditions.append(_condition("unity_versions", filters.unity_version))
    if filters.unity_version_major:
        conditions.append(_condition("unity_version_major", filters.unity_version_major))
    if filters.render_pipeline:
        conditions.append(_condition("render_pipelines", filters.render_pipeline))
    return {"must": conditions} if conditions else None


__all__ = ["build_qdrant_filter"]
