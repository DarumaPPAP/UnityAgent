"""Context Explorer projection from canonical Context Pack metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from builder.graph_builder import AgentGraph, GraphEdge, GraphNode


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_repository_relative_path(value: str) -> str:
    """Normalize a repository path and reject traversal or executable schemes."""
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"executable or external URL is forbidden: {value}")
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path traversal is forbidden: {value}")
    return path.as_posix()


def build_context_graph(root: Path) -> AgentGraph:
    graph = AgentGraph(view="context")
    pack_dir = root / ".ai/context-packs"
    packs: dict[str, dict[str, Any]] = {}
    for path in sorted(pack_dir.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        packs[str(document["id"])] = (path, document)

    for context_id, (path, document) in sorted(packs.items()):
        metadata = document.get("metadata", {})
        graph.add_node(
            GraphNode(
                id=f"context:{context_id}",
                type="context",
                label=metadata.get("title", context_id),
                metadata={
                    "summary": metadata.get("summary", []),
                    "purpose": metadata.get("purpose", []),
                    "decisions": metadata.get("decisions", []),
                    "forbidden": metadata.get("forbidden", []),
                    "related": metadata.get("related", []),
                    "priority": metadata.get("priority", "normal"),
                    "tags": metadata.get("tags", []),
                    "provenance": {
                        "source_path": validate_repository_relative_path(path.relative_to(root).as_posix()),
                        "reason": "canonical_binding",
                        "source_hash": source_hash(path),
                    },
                },
            )
        )

    for context_id, (_, document) in sorted(packs.items()):
        for related in document.get("metadata", {}).get("related", []) or []:
            target = str(related["id"])
            if target in packs:
                graph.add_edge(
                    GraphEdge(
                        source=f"context:{context_id}",
                        target=f"context:{target}",
                        relation=str(related["relation"]),
                        metadata={
                            "reason": related["reason"],
                            "source_path": validate_repository_relative_path(related["source_ref"].split("#", 1)[0]),
                            "provenance": "explicit_metadata_relation",
                        },
                    )
                )
    return graph
