"""Phase 8.9 Graph Artifact Validator foundation.

Validates Graph Observatory artifacts before visualization.
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]


def validate_graph(graph: Dict) -> ValidationResult:
    errors = []

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    node_ids = {node.get("id") for node in nodes}

    for node in nodes:
        if not node.get("id"):
            errors.append("Node id is missing")

    for edge in edges:
        if edge.get("source") not in node_ids:
            errors.append(f"Missing edge source: {edge.get('source')}")
        if edge.get("target") not in node_ids:
            errors.append(f"Missing edge target: {edge.get('target')}")
        if not edge.get("relation"):
            errors.append("Edge relation is missing")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
    )
