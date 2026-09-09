"""Bounded, deterministic query planning for complex retrieval requests."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from RAG.Contracts.models import RetrievalCandidate, RetrievalFilters, deterministic_id
from RAG.Query.extract_filters import extract_filters
from RAG.Query.normalize_query import normalize_query
from RAG.Ranking.rrf import RRFConfig, reciprocal_rank_fusion


@dataclass(frozen=True)
class PlannedSubquery:
    subquery_id: str
    query: str
    purpose: str
    filters: RetrievalFilters
    source_hints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "subquery_id": self.subquery_id,
            "query": self.query,
            "purpose": self.purpose,
            "filters": self.filters.to_dict(),
            "source_hints": list(self.source_hints),
        }


@dataclass(frozen=True)
class QueryPlan:
    plan_id: str
    original_query: str
    subqueries: tuple[PlannedSubquery, ...]
    max_subqueries: int
    revision: str = "query-plan-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "subqueries": [item.to_dict() for item in self.subqueries],
            "max_subqueries": int(self.max_subqueries),
            "revision": self.revision,
        }


@dataclass(frozen=True)
class SubqueryTrace:
    subquery_id: str
    purpose: str
    query_hash: str
    candidate_count: int
    status: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subquery_id": self.subquery_id,
            "purpose": self.purpose,
            "query_hash": self.query_hash,
            "candidate_count": int(self.candidate_count),
            "status": self.status,
            "error": self.error,
        }


@dataclass(frozen=True)
class PlannedRetrievalResult:
    candidates: tuple[RetrievalCandidate, ...]
    subquery_traces: tuple[SubqueryTrace, ...]
    diagnostics: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "subqueries": [item.to_dict() for item in self.subquery_traces],
            "diagnostics": list(self.diagnostics),
        }


def build_query_plan(
    query: str,
    *,
    filters: RetrievalFilters | Mapping[str, Any] | None = None,
    max_subqueries: int = 3,
) -> QueryPlan:
    """Create up to three deterministic views without LLM-generated guesses."""

    if not 0 <= int(max_subqueries) <= 4:
        raise ValueError("max_subqueries must be 0..4")
    normalized = normalize_query(query)
    extracted = extract_filters(normalized)
    explicit = filters.to_dict() if isinstance(filters, RetrievalFilters) else dict(filters or {})
    merged = extracted.to_dict()
    merged.update({key: value for key, value in explicit.items() if value is not None})
    merged_filters = RetrievalFilters.from_mapping(merged)
    if int(max_subqueries) == 0:
        return QueryPlan(
            plan_id=deterministic_id("plan", normalized.query_hash, 0),
            original_query=query,
            subqueries=(),
            max_subqueries=0,
        )

    candidates: list[tuple[str, str]] = []
    if normalized.technical_tokens:
        candidates.append(("technical_identifier", " ".join(normalized.technical_tokens)))
    candidates.append(("intent", normalized.normalized))
    if merged_filters.unity_version or merged_filters.render_pipeline or merged_filters.pipeline_version:
        candidates.append(("version_pipeline_constraint", normalized.normalized))

    subqueries: list[PlannedSubquery] = []
    seen: set[str] = set()
    for purpose, subquery in candidates:
        key = subquery.casefold()
        if key in seen:
            continue
        seen.add(key)
        subqueries.append(PlannedSubquery(
            subquery_id=deterministic_id("subq", normalized.query_hash, purpose, subquery),
            query=subquery,
            purpose=purpose,
            filters=merged_filters,
        ))
        if len(subqueries) >= int(max_subqueries):
            break
    return QueryPlan(
        plan_id=deterministic_id("plan", normalized.query_hash, merged_filters.to_dict(), len(subqueries)),
        original_query=query,
        subqueries=tuple(subqueries),
        max_subqueries=int(max_subqueries),
    )


def execute_query_plan(
    plan: QueryPlan,
    retrieve: Callable[[PlannedSubquery], Sequence[RetrievalCandidate]],
    *,
    rrf_config: RRFConfig | None = None,
    max_workers: int = 3,
    candidate_limit: int = 200,
) -> PlannedRetrievalResult:
    """Run bounded subqueries concurrently and fuse them deterministically."""

    if not 1 <= int(max_workers) <= 8:
        raise ValueError("max_workers must be 1..8")
    if not 1 <= int(candidate_limit) <= 200:
        raise ValueError("candidate_limit must be 1..200")
    if not plan.subqueries:
        return PlannedRetrievalResult((), ())
    traces: dict[str, SubqueryTrace] = {}
    lists: dict[str, list[RetrievalCandidate]] = {}
    workers = min(int(max_workers), len(plan.subqueries))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rag-subquery") as executor:
        futures = {executor.submit(retrieve, subquery): subquery for subquery in plan.subqueries}
        for future in as_completed(futures):
            subquery = futures[future]
            try:
                values = list(future.result())[: int(candidate_limit)]
                lists[subquery.subquery_id] = values
                traces[subquery.subquery_id] = SubqueryTrace(
                    subquery_id=subquery.subquery_id,
                    purpose=subquery.purpose,
                    query_hash=normalize_query(subquery.query).query_hash,
                    candidate_count=len(values),
                    status="ok",
                )
            except Exception as exc:  # A failed subquery must be visible, not hidden.
                lists[subquery.subquery_id] = []
                traces[subquery.subquery_id] = SubqueryTrace(
                    subquery_id=subquery.subquery_id,
                    purpose=subquery.purpose,
                    query_hash=normalize_query(subquery.query).query_hash,
                    candidate_count=0,
                    status="failed",
                    error=str(exc),
                )
    ordered_traces = tuple(traces[item.subquery_id] for item in plan.subqueries)
    diagnostics = tuple(
        {"code": "subquery_failure", "subquery_id": trace.subquery_id, "message": trace.error}
        for trace in ordered_traces
        if trace.status != "ok"
    )
    fused = reciprocal_rank_fusion(lists, config=rrf_config, limit=candidate_limit)
    return PlannedRetrievalResult(tuple(fused), ordered_traces, diagnostics)


__all__ = [
    "PlannedRetrievalResult",
    "PlannedSubquery",
    "QueryPlan",
    "SubqueryTrace",
    "build_query_plan",
    "execute_query_plan",
]
