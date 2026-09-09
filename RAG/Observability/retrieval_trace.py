"""Structured, privacy-light trace for one retrieval request."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalTrace:
    request_id: str
    query_hash: str
    route_id: str
    execution_profile: str
    query_kind: str
    filters: dict[str, Any]
    backend: str
    backend_revision: str
    retrieval_methods: list[str] = field(default_factory=list)
    candidate_count: int = 0
    returned_count: int = 0
    grounded_count: int = 0
    latency_ms: float | None = None
    truncated: bool = False
    fallback_used: bool = False
    source_failures: list[dict[str, Any]] = field(default_factory=list)
    top_source_refs: list[str] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    ranking_config: dict[str, Any] = field(default_factory=dict)
    query_plan: dict[str, Any] | None = None
    subqueries: list[dict[str, Any]] = field(default_factory=list)
    graph_expansion: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "request_id": self.request_id,
            "query_hash": self.query_hash,
            "route_id": self.route_id,
            "execution_profile": self.execution_profile,
            "query_kind": self.query_kind,
            "filters": self.filters,
            "backend": self.backend,
            "backend_revision": self.backend_revision,
            "retrieval_methods": list(self.retrieval_methods),
            "counts": {
                "candidate": int(self.candidate_count),
                "returned": int(self.returned_count),
                "selected": int(self.grounded_count),
                "grounded": int(self.grounded_count),
            },
            "latency_ms": None if self.latency_ms is None else round(float(self.latency_ms), 3),
            "truncated": bool(self.truncated),
            "fallback_used": bool(self.fallback_used),
            "source_failures": list(self.source_failures),
            "top_source_refs": list(self.top_source_refs),
            "diagnostics": list(self.diagnostics),
            "ranking_config": dict(self.ranking_config),
            "query_plan": self.query_plan,
            "subqueries": list(self.subqueries),
            "graph_expansion": self.graph_expansion,
        }
