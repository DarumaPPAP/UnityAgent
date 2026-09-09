"""Extract only explicitly written metadata from a query."""

from __future__ import annotations

import re
from typing import Any

from RAG.Contracts.models import RetrievalFilters
from RAG.Query.normalize_query import NormalizedQuery, normalize_query


UNITY_VERSION_RE = re.compile(r"\b(?:20\d{2}|6000)(?:\.\d+|\.x)+(?:f\d+)?\b", re.IGNORECASE)
PIPELINE_VERSION_RE = re.compile(r"\b(?:urp|hdrp)\s*(?:version\s*)?(\d+(?:\.\d+)?\+?)(?!\w)", re.IGNORECASE)

PLATFORM_ALIASES = {
    "switch": "Switch",
    "switch2": "Switch2",
    "ps4": "PS4",
    "ps5": "PS5",
    "xbox": "Xbox",
    "pc": "PC",
    "android": "Android",
    "ios": "iOS",
}
DOMAIN_ALIASES = {
    "shader": "shader",
    "shaders": "shader",
    "rendering": "rendering",
    "renderer": "rendering",
    "performance": "performance",
    "camera": "camera",
    "cameras": "camera",
    "mcp": "mcp",
    "rag": "rag",
}


def extract_filters(query: str | NormalizedQuery) -> RetrievalFilters:
    """Return filters present in the query; unknown dimensions remain unset."""

    normalized = query if isinstance(query, NormalizedQuery) else normalize_query(query)
    lowered = normalized.raw.casefold()
    version_match = UNITY_VERSION_RE.search(lowered)
    unity_version = version_match.group(0) if version_match else None
    major = unity_version.split(".", 1)[0] if unity_version else None

    pipeline = None
    if re.search(r"\burp(?:\b|[_-])|\buniversal render pipeline\b", lowered):
        pipeline = "URP"
    elif re.search(r"\bhdrp(?:\b|[_-])|\bhigh definition render pipeline\b", lowered):
        pipeline = "HDRP"
    elif re.search(r"\bbuilt[- ]?in\b", lowered):
        pipeline = "Built-in"
    pipeline_version_match = PIPELINE_VERSION_RE.search(lowered)

    platforms = [PLATFORM_ALIASES[token] for token in normalized.tokens if token in PLATFORM_ALIASES]
    domains = [DOMAIN_ALIASES[token] for token in normalized.tokens if token in DOMAIN_ALIASES]
    return RetrievalFilters(
        unity_version=unity_version,
        unity_version_major=major,
        render_pipeline=pipeline,
        pipeline_version=pipeline_version_match.group(1) if pipeline_version_match else None,
        platforms=tuple(dict.fromkeys(platforms)),
        domains=tuple(dict.fromkeys(domains)),
    )
