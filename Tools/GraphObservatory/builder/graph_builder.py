"""Phase 8 Graph Observatory graph builder foundation.

Converts canonical agent artifacts into a visualization-friendly graph model.
The exported graph is a derived view. YAML contracts remain the source of truth.
"""

from dataclasses import dataclass, field
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

    def add_node(self, node: GraphNode) -> None:
        self.nodes.append(node)

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.__dict__ for node in self.nodes],
            "edges": [edge.__dict__ for edge in self.edges],
            "metadata": {
                "generated_by": "GraphObservatory",
                "view": "derived"
            }
        }
