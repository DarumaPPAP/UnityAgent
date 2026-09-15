"""Read-only Context Explorer map built from canonical Context Pack metadata.

This module deliberately avoids a generic runtime graph abstraction. It parses the
canonical Context/Packs metadata into a small derived map used only by the offline
human-maintenance viewer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


CANONICAL_CONTEXT_PACKS = Path("Context/Packs")
SCHEMA_VERSION = "1.0"
MAP_KIND = "unityagent-context-map"


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


@dataclass(frozen=True)
class ContextNode:
    id: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextRelation:
    source: str
    target: str
    relation: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextMap:
    nodes: list[ContextNode] = field(default_factory=list)
    edges: list[ContextRelation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        nodes = sorted(self.nodes, key=lambda node: node.id)
        edges = sorted(self.edges, key=lambda edge: (edge.source, edge.target, edge.relation))
        return {
            "metadata": {
                "schema_version": SCHEMA_VERSION,
                "kind": MAP_KIND,
                "generated_from": CANONICAL_CONTEXT_PACKS.as_posix(),
                "generated_by": "ContextExplorer",
                "read_only": True,
            },
            "nodes": [
                {"id": node.id, "type": "context", "label": node.label, "metadata": node.metadata}
                for node in nodes
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "relation": edge.relation,
                    "metadata": edge.metadata,
                }
                for edge in edges
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _list_value(metadata: dict[str, Any], key: str, source: Path) -> list[Any]:
    value = metadata.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"metadata.{key} must be a list: {source.as_posix()}")
    return value


def load_context_map(root: Path) -> ContextMap:
    """Parse Context/Packs into a deterministic read-only ContextMap."""
    pack_dir = root / CANONICAL_CONTEXT_PACKS
    if not pack_dir.is_dir():
        raise FileNotFoundError(
            f"canonical Context Pack directory is missing: {CANONICAL_CONTEXT_PACKS.as_posix()}"
        )

    packs: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(pack_dir.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            raise ValueError(f"Context Pack root must be a mapping: {path.relative_to(root).as_posix()}")
        context_id = str(document.get("id") or "").strip()
        if not context_id:
            raise ValueError(f"Context Pack is missing id: {path.relative_to(root).as_posix()}")
        if context_id in packs:
            raise ValueError(f"duplicate Context Pack id: {context_id}")
        metadata = document.get("metadata", {}) or {}
        if not isinstance(metadata, dict):
            raise ValueError(f"metadata must be a mapping: {path.relative_to(root).as_posix()}")
        packs[context_id] = (path, document)

    if not packs:
        raise ValueError(f"no canonical Context Packs found under {CANONICAL_CONTEXT_PACKS.as_posix()}")

    context_map = ContextMap()

    for context_id, (path, document) in sorted(packs.items()):
        metadata = document.get("metadata", {}) or {}
        relative_path = validate_repository_relative_path(path.relative_to(root).as_posix())
        primary_skill = str(document.get("primary_skill") or "").strip()
        if primary_skill:
            primary_skill = validate_repository_relative_path(primary_skill)

        context_map.nodes.append(
            ContextNode(
                id=f"context:{context_id}",
                label=str(metadata.get("title") or context_id),
                metadata={
                    "summary": _list_value(metadata, "summary", path),
                    "purpose": _list_value(metadata, "purpose", path),
                    "decisions": _list_value(metadata, "decisions", path),
                    "forbidden": _list_value(metadata, "forbidden", path),
                    "related": _list_value(metadata, "related", path),
                    "priority": str(metadata.get("priority") or "normal"),
                    "tags": _list_value(metadata, "tags", path),
                    "primary_skill": primary_skill,
                    "provenance": {
                        "source_path": relative_path,
                        "reason": "canonical_context_pack",
                        "source_hash": source_hash(path),
                    },
                },
            )
        )

    for context_id, (path, document) in sorted(packs.items()):
        metadata = document.get("metadata", {}) or {}
        for related in _list_value(metadata, "related", path):
            if not isinstance(related, dict):
                raise ValueError(f"metadata.related item must be a mapping: {path.relative_to(root).as_posix()}")
            target = str(related.get("id") or "").strip()
            relation = str(related.get("relation") or "").strip()
            reason = str(related.get("reason") or "").strip()
            source_ref = str(related.get("source_ref") or "").strip()
            if not target or not relation or not reason or not source_ref:
                raise ValueError(
                    f"metadata.related requires id/relation/reason/source_ref: {path.relative_to(root).as_posix()}"
                )
            if target not in packs:
                continue
            source_path = validate_repository_relative_path(source_ref.split("#", 1)[0])
            context_map.edges.append(
                ContextRelation(
                    source=f"context:{context_id}",
                    target=f"context:{target}",
                    relation=relation,
                    metadata={
                        "reason": reason,
                        "source_path": source_path,
                        "provenance": "explicit_context_metadata_relation",
                    },
                )
            )

    errors = validate_context_map(context_map.to_dict())
    if errors:
        raise ValueError("invalid generated ContextMap: " + "; ".join(errors))
    return context_map


def validate_context_map(document: dict[str, Any]) -> list[str]:
    """Dependency-free validation for the generated Context Explorer artifact."""
    errors: list[str] = []
    metadata = document.get("metadata", {})
    if not isinstance(metadata, dict):
        return ["metadata must be an object"]

    required_metadata = {
        "schema_version": SCHEMA_VERSION,
        "kind": MAP_KIND,
        "generated_from": CANONICAL_CONTEXT_PACKS.as_posix(),
        "generated_by": "ContextExplorer",
        "read_only": True,
    }
    for field, expected in required_metadata.items():
        if metadata.get(field) != expected:
            errors.append(f"metadata.{field} must be {expected!r}")

    nodes = document.get("nodes", [])
    edges = document.get("edges", [])
    if not isinstance(nodes, list):
        errors.append("nodes must be a list")
        nodes = []
    if not isinstance(edges, list):
        errors.append("edges must be a list")
        edges = []

    node_ids: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("node must be an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            errors.append("node id is required")
            continue
        node_ids.append(node_id)
        if node.get("type") != "context":
            errors.append(f"node type must be context: {node_id}")
        provenance = (node.get("metadata") or {}).get("provenance") or {}
        if not provenance.get("source_path"):
            errors.append(f"node provenance.source_path is required: {node_id}")
        if not provenance.get("source_hash"):
            errors.append(f"node provenance.source_hash is required: {node_id}")

    if len(set(node_ids)) != len(node_ids):
        errors.append("duplicate node id")

    known = set(node_ids)
    for edge in edges:
        if not isinstance(edge, dict):
            errors.append("edge must be an object")
            continue
        source = edge.get("source")
        target = edge.get("target")
        relation = edge.get("relation")
        if source not in known:
            errors.append(f"edge source does not exist: {source}")
        if target not in known:
            errors.append(f"edge target does not exist: {target}")
        if not relation:
            errors.append("edge relation is required")

    return errors
