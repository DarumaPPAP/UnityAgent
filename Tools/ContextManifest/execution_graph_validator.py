#!/usr/bin/env python3
"""Validate one derived Execution Graph against .ai/graph-contract.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_manifest_runtime import GRAPH_CONTRACT_PATH, load_yaml


def validate_execution_graph(root: Path, graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    contract = load_yaml(root / GRAPH_CONTRACT_PATH)
    allowed_node_types = set(contract.get("node_types", []) or [])
    allowed_edge_types = set(contract.get("edge_types", []) or [])
    allowed_reasons = set(contract.get("provenance", {}).get("reasons", []) or [])

    if graph.get("graph_kind") != "execution":
        errors.append("Execution Graph graph_kind must be execution.")
    if not graph.get("manifest_id"):
        errors.append("Execution Graph manifest_id is required.")

    nodes = graph.get("nodes", [])
    if not isinstance(nodes, list):
        return errors + ["Execution Graph nodes must be a list."]

    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("Execution Graph node must be a mapping.")
            continue
        node_id = str(node.get("id", "")).strip()
        node_type = str(node.get("type", "")).strip()
        if not node_id:
            errors.append("Execution Graph node id is required.")
            continue
        if node_id in node_ids:
            errors.append(f"Duplicate Execution Graph node id: {node_id}")
        node_ids.add(node_id)
        if node_type not in allowed_node_types:
            errors.append(f"Unsupported Execution Graph node type: {node_type}")
        if not node_id.startswith(f"{node_type}:"):
            errors.append(f"Node id/type prefix mismatch: {node_id} vs {node_type}")

        provenance = node.get("provenance", {})
        if not isinstance(provenance, dict):
            errors.append(f"Node provenance must be a mapping: {node_id}")
            continue
        if not provenance.get("source_path"):
            errors.append(f"Node provenance source_path is required: {node_id}")
        reason = provenance.get("reason")
        if reason not in allowed_reasons:
            errors.append(f"Unsupported node provenance reason: {node_id}={reason}")

    root_node = graph.get("root_node")
    if root_node not in node_ids:
        errors.append(f"Execution Graph root_node does not exist: {root_node}")

    edges = graph.get("edges", [])
    if not isinstance(edges, list):
        return errors + ["Execution Graph edges must be a list."]

    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        if not isinstance(edge, dict):
            errors.append("Execution Graph edge must be a mapping.")
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        edge_type = str(edge.get("type", ""))
        edge_key = (source, target, edge_type)
        if edge_key in seen_edges:
            errors.append(f"Duplicate Execution Graph edge: {edge_key}")
        seen_edges.add(edge_key)
        if source not in node_ids:
            errors.append(f"Execution Graph edge source does not exist: {source}")
        if target not in node_ids:
            errors.append(f"Execution Graph edge target does not exist: {target}")
        if edge_type not in allowed_edge_types:
            errors.append(f"Unsupported Execution Graph edge type: {edge_type}")
        reason = edge.get("reason")
        if reason not in allowed_reasons:
            errors.append(f"Unsupported Execution Graph edge reason: {edge_key}={reason}")

    return errors
