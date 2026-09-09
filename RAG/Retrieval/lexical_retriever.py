"""Deterministic lexical MVP backend.

Technical identifiers get an exact-match path while ordinary words use token overlap.
All filtering happens before ranking so a hard project/platform boundary cannot be
overridden by a high lexical score.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

from RAG.Contracts.models import RetrievalCandidate, RetrievalFilters, RetrievalRequest
from RAG.Query.normalize_query import NormalizedQuery, normalize_query


TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:[_./:+-][A-Za-z0-9]+)*|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+",
    re.UNICODE,
)
SEPARATOR_RE = re.compile(r"[_./:+-]+")


@dataclass(frozen=True)
class LexicalScoringWeights:
    exact_technical_token: float = 20.0
    token_overlap: float = 10.0
    domain_match: float = 4.0
    unity_version_match: float = 3.0
    render_pipeline_match: float = 3.0
    pipeline_version_match: float = 3.0
    platform_match: float = 3.0
    reviewed_or_verified: float = 1.0


def _tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value)
    result: set[str] = set()
    for match in TOKEN_RE.finditer(text.casefold()):
        token = match.group(0)
        result.add(token)
        result.update(piece for piece in SEPARATOR_RE.split(token) if len(piece) >= 2)
    return result


def _metadata_values(metadata: dict[str, Any], *keys: str) -> set[str]:
    values: list[Any] = []
    for key in keys:
        if key in metadata:
            values.extend(metadata[key] if isinstance(metadata[key], (list, tuple, set)) else [metadata[key]])
    return {str(value).casefold() for value in values if str(value).strip()}


def _version_matches(wanted: str | None, values: set[str]) -> bool:
    if not wanted:
        return False
    wanted_folded = wanted.casefold()
    wanted_major = wanted_folded.split(".", 1)[0]
    for value in values:
        if value == wanted_folded:
            return True
        if value.endswith(".x") and wanted_folded.startswith(value[:-2] + "."):
            return True
        if wanted_folded.endswith(".x") and value.startswith(wanted_folded[:-2] + "."):
            return True
        if value.split(".", 1)[0] == wanted_major and value.endswith(".x"):
            return True
    return False


def matches_hard_filters(candidate: RetrievalCandidate, filters: RetrievalFilters) -> bool:
    metadata = candidate.metadata
    if filters.repository and str(metadata.get("repository") or "").casefold() != filters.repository.casefold():
        return False
    if filters.project_id and str(metadata.get("project_id") or "").casefold() != filters.project_id.casefold():
        return False
    if filters.source_kind and candidate.source_kind.casefold() != filters.source_kind.casefold():
        return False
    if filters.document_id and str(candidate.document_id or "").casefold() != filters.document_id.casefold():
        return False
    if filters.platforms:
        candidate_platforms = _metadata_values(metadata, "platforms", "platform")
        if not candidate_platforms or not {item.casefold() for item in filters.platforms}.intersection(candidate_platforms):
            return False
    return True


def score_candidate(
    candidate: RetrievalCandidate,
    query: str | NormalizedQuery,
    filters: RetrievalFilters | None = None,
    *,
    weights: LexicalScoringWeights | None = None,
) -> dict[str, float]:
    normalized = query if isinstance(query, NormalizedQuery) else normalize_query(query)
    filters = filters or RetrievalFilters()
    weights = weights or LexicalScoringWeights()
    searchable = _tokens(candidate.searchable_text())
    exact_query_tokens = set(normalized.technical_tokens)
    exact_matches = exact_query_tokens.intersection(searchable)
    overlap = set(normalized.tokens).intersection(searchable)
    score = len(exact_matches) * weights.exact_technical_token
    score += len(overlap) * weights.token_overlap

    candidate_domains = _metadata_values(candidate.metadata, "domains", "domain")
    requested_domains = {value.casefold() for value in filters.domains}
    score += len(candidate_domains.intersection(requested_domains)) * weights.domain_match

    versions = _metadata_values(candidate.metadata, "unity_versions", "unity_version", "unityVersions")
    if _version_matches(filters.unity_version, versions) or (
        filters.unity_version_major and any(value.split(".", 1)[0] == filters.unity_version_major.casefold() for value in versions)
    ):
        score += weights.unity_version_match

    pipelines = _metadata_values(candidate.metadata, "render_pipelines", "render_pipeline", "renderPipelines")
    if filters.render_pipeline and filters.render_pipeline.casefold() in pipelines:
        score += weights.render_pipeline_match
    pipeline_versions = _metadata_values(candidate.metadata, "pipeline_version", "pipeline_versions", "pipelineVersion")
    if filters.pipeline_version and any(
        value == filters.pipeline_version.casefold()
        or value.rstrip("+") == filters.pipeline_version.casefold().rstrip("+")
        for value in pipeline_versions
    ):
        score += weights.pipeline_version_match

    candidate_platforms = _metadata_values(candidate.metadata, "platforms", "platform")
    if filters.platforms and {value.casefold() for value in filters.platforms}.intersection(candidate_platforms):
        score += weights.platform_match

    status = str(candidate.review_status or candidate.metadata.get("review_status") or candidate.metadata.get("status") or "").casefold()
    confidence = str(candidate.confidence or "").casefold()
    if status in {"reviewed", "verified"} or confidence in {"reviewed", "verified"}:
        score += weights.reviewed_or_verified

    return {
        "lexical": float(score),
        "exact_token_matches": float(len(exact_matches)),
        "token_overlap": float(len(overlap)),
    }


def rank_candidates(
    candidates: Iterable[RetrievalCandidate],
    request: RetrievalRequest,
    *,
    weights: LexicalScoringWeights | None = None,
) -> list[RetrievalCandidate]:
    ranked: list[RetrievalCandidate] = []
    for candidate in candidates:
        if not matches_hard_filters(candidate, request.filters):
            continue
        scores = score_candidate(candidate, request.normalized_query, request.filters, weights=weights)
        # Review/confidence is only a tie-break bonus. It must never manufacture
        # an answer for a query with no lexical evidence.
        if scores["exact_token_matches"] <= 0 and scores["token_overlap"] <= 0:
            continue
        candidate.lexical_score = scores["lexical"]
        ranked.append(candidate)
    ranked.sort(key=lambda item: (-item.lexical_score, item.candidate_id))
    return ranked[: request.candidate_k]


class LocalLexicalBackend:
    """In-memory deterministic backend populated by read-only source adapters."""

    revision = "local-lexical-v1"

    def __init__(self, candidates: Iterable[RetrievalCandidate] = ()) -> None:
        self._candidates = tuple(candidates)

    def capabilities(self) -> set[str]:
        return {"lexical", "filtering"}

    def retrieve(self, request: RetrievalRequest) -> list[RetrievalCandidate]:
        return rank_candidates(self._candidates, request)
