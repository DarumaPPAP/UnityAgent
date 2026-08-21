"""Graph Observatory edge generation foundation.

Edges are derived from canonical YAML relationships.
Graph remains a projection; canonical files remain the source of truth.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    metadata: Dict = field(default_factory=dict)


class EdgeResolver:
    def resolve_requires(self, source_id: str, target_ids: List[str]) -> List[GraphEdge]:
        return [
            GraphEdge(source=source_id, target=target_id, relation="requires")
            for target_id in target_ids
        ]

    def resolve_prohibits(self, source_id: str, target_ids: List[str]) -> List[GraphEdge]:
        return [
            GraphEdge(source=source_id, target=target_id, relation="prohibits")
            for target_id in target_ids
        ]

    def resolve_evaluated_by(self, task_id: str, grader_id: str) -> GraphEdge:
        return GraphEdge(
            source=task_id,
            target=grader_id,
            relation="evaluated_by",
        )

    def resolve_produces_evidence(self, attempt_id: str, evidence_id: str) -> GraphEdge:
        return GraphEdge(
            source=attempt_id,
            target=evidence_id,
            relation="produces_evidence",
        )
