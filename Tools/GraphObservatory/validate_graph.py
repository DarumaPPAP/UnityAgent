"""Small dependency-free validator for generated Graph Observatory artifacts."""

from __future__ import annotations

from typing import Any


def validate_graph(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    metadata = document.get("metadata", {})
    for field in ("version", "generated_from"):
        if not metadata.get(field):
            errors.append(f"metadata.{field} is required")
    node_ids = {node.get("id") for node in document.get("nodes", [])}
    if None in node_ids:
        errors.append("node id is required")
    if len(node_ids) != len(document.get("nodes", [])):
        errors.append("duplicate node id")
    for edge in document.get("edges", []):
        if edge.get("source") not in node_ids:
            errors.append(f"edge source does not exist: {edge.get('source')}")
        if edge.get("target") not in node_ids:
            errors.append(f"edge target does not exist: {edge.get('target')}")
        if not edge.get("relation"):
            errors.append("edge relation is required")
    return errors
