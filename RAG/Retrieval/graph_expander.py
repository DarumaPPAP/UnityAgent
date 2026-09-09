"""Bounded Knowledge Graph expansion, separate from Orchestration graphs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
import re
from typing import Any

from RAG.Contracts.models import RetrievalCandidate


_URI_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]+$")
_ALLOWED_RELATIONS = {
    "related",
    "supports",
    "depends_on",
    "contradicts",
    "derived_from",
    "same_topic",
    "diagnoses",
}


@dataclass(frozen=True)
class KnowledgeRelation:
    relation_id: str
    source_candidate_id: str
    target_candidate_id: str
    relation_type: str
    provenance_ref: str

    @classmethod
    def from_mapping(cls, source_id: str, value: Mapping[str, Any]) -> "KnowledgeRelation":
        relation_id = str(value.get("relation_id") or value.get("id") or "").strip()
        target = str(value.get("target_candidate_id") or value.get("target_id") or "").strip()
        relation_type = str(value.get("relation_type") or value.get("relation") or "related").casefold().strip()
        provenance = str(value.get("provenance_ref") or value.get("relation_ref") or "").strip()
        if not relation_id or not target:
            raise ValueError("relation_id and target_candidate_id are required")
        if relation_type not in _ALLOWED_RELATIONS:
            raise ValueError(f"unsupported knowledge relation: {relation_type}")
        if not _URI_RE.fullmatch(provenance):
            raise ValueError("relation provenance_ref must be a URI")
        return cls(relation_id, str(source_id), target, relation_type, provenance)

    def to_dict(self) -> dict[str, str]:
        return {
            "relation_id": self.relation_id,
            "source_candidate_id": self.source_candidate_id,
            "target_candidate_id": self.target_candidate_id,
            "relation_type": self.relation_type,
            "provenance_ref": self.provenance_ref,
        }


@dataclass(frozen=True)
class GraphExpansionConfig:
    max_hops: int = 1
    max_nodes: int = 32

    def __post_init__(self) -> None:
        if not 0 <= int(self.max_hops) <= 4:
            raise ValueError("max_hops must be 0..4")
        if not 1 <= int(self.max_nodes) <= 200:
            raise ValueError("max_nodes must be 1..200")


@dataclass(frozen=True)
class GraphExpansionResult:
    candidates: tuple[RetrievalCandidate, ...]
    expanded_count: int
    max_hops: int
    diagnostics: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "expanded_count": int(self.expanded_count),
            "max_hops": int(self.max_hops),
            "diagnostics": list(self.diagnostics),
        }


class KnowledgeGraphExpander:
    """Expand only explicit Knowledge relations with auditable provenance."""

    def __init__(
        self,
        relations: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
        *,
        config: GraphExpansionConfig | None = None,
    ) -> None:
        self.relations = relations or {}
        self.config = config or GraphExpansionConfig()

    def expand(
        self,
        seeds: Iterable[RetrievalCandidate],
        *,
        candidate_lookup: Mapping[str, RetrievalCandidate] | None = None,
    ) -> GraphExpansionResult:
        result = list(seeds)
        lookup = dict(candidate_lookup or {item.candidate_id: item for item in result})
        visited = {item.candidate_id for item in result}
        frontier = list(result)
        diagnostics: list[dict[str, Any]] = []
        expanded_count = 0
        for hop in range(1, int(self.config.max_hops) + 1):
            next_frontier: list[RetrievalCandidate] = []
            for source in frontier:
                raw_relations = self.relations.get(source.candidate_id, ())
                for raw_relation in raw_relations:
                    if len(result) >= int(self.config.max_nodes):
                        diagnostics.append({"code": "graph_budget_exhausted", "max_nodes": self.config.max_nodes})
                        return GraphExpansionResult(tuple(result), expanded_count, self.config.max_hops, tuple(diagnostics))
                    try:
                        relation = KnowledgeRelation.from_mapping(source.candidate_id, raw_relation)
                    except (TypeError, ValueError) as exc:
                        diagnostics.append({
                            "code": "invalid_relation",
                            "source_candidate_id": source.candidate_id,
                            "message": str(exc),
                        })
                        continue
                    if relation.target_candidate_id in visited:
                        continue
                    target = lookup.get(relation.target_candidate_id)
                    if target is None:
                        diagnostics.append({
                            "code": "relation_target_missing",
                            "relation_id": relation.relation_id,
                            "target_candidate_id": relation.target_candidate_id,
                        })
                        continue
                    copied = deepcopy(target)
                    copied.metadata = dict(copied.metadata)
                    copied.metadata.update({
                        "graph_hop": hop,
                        "expanded_from": source.candidate_id,
                        "relation_type": relation.relation_type,
                        "relation_id": relation.relation_id,
                        "relation_provenance": relation.provenance_ref,
                    })
                    copied.provenance = replace(
                        copied.provenance,
                        relation_refs=tuple(dict.fromkeys((*copied.provenance.relation_refs, relation.provenance_ref))),
                    )
                    result.append(copied)
                    next_frontier.append(copied)
                    visited.add(copied.candidate_id)
                    expanded_count += 1
            frontier = next_frontier
            if not frontier:
                break
        return GraphExpansionResult(tuple(result), expanded_count, self.config.max_hops, tuple(diagnostics))


def expand_candidates(
    candidates: Iterable[RetrievalCandidate],
    *,
    max_hops: int = 0,
    relations: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    candidate_lookup: Mapping[str, RetrievalCandidate] | None = None,
    max_nodes: int = 32,
    return_result: bool = False,
) -> list[RetrievalCandidate] | GraphExpansionResult:
    """Backward-compatible helper; defaults to the safe no-expansion behavior."""

    result = KnowledgeGraphExpander(
        relations,
        config=GraphExpansionConfig(max_hops=max_hops, max_nodes=max_nodes),
    ).expand(candidates, candidate_lookup=candidate_lookup)
    return result if return_result else list(result.candidates)


__all__ = [
    "GraphExpansionConfig",
    "GraphExpansionResult",
    "KnowledgeGraphExpander",
    "KnowledgeRelation",
    "expand_candidates",
]
