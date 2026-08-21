"""Canonical Graph Observatory model used by all derived projections.

Converts canonical agent artifacts into a visualization-friendly graph model.
The exported graph is a derived view. YAML contracts remain the source of truth.
"""

from dataclasses import dataclass, field
import json
from typing import Any


@dataclass
class GraphNode:
    id: str
    type: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentGraph:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    view: str = "derived"
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        self.nodes.append(node)

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def add_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def to_dict(self) -> dict[str, Any]:
        nodes = sorted(self.nodes, key=lambda node: node.id)
        edges = sorted(self.edges, key=lambda edge: (edge.source, edge.target, edge.relation))
        metadata = {
            "version": "1.0",
            "generated_from": "canonical-yaml",
            "generated_by": "GraphObservatory",
            "view": self.view,
            **self.metadata,
        }
        return {
            "nodes": [node.__dict__ for node in nodes],
            "edges": [edge.__dict__ for edge in edges],
            "metadata": metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
