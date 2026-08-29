#!/usr/bin/env python3
"""Canonical Phase 8 repository reference resolver.

Only canonical repository-relative paths are accepted. Legacy compatibility:// URIs and
.ai paths are rejected after cutover instead of being silently rewritten.
"""
from __future__ import annotations
from pathlib import Path


class ReferenceResolutionError(ValueError):
    pass


def resolve_reference(reference: str) -> str:
    value = str(reference).strip()
    if not value:
        raise ReferenceResolutionError("reference is required")
    if value.startswith("compatibility://"):
        raise ReferenceResolutionError("compatibility URI is forbidden after Phase 8 cutover")
    base = value.split("#", 1)[0]
    if base == ".ai" or base.startswith(".ai/"):
        raise ReferenceResolutionError("legacy .ai path is forbidden after Phase 8 cutover")
    return value


def resolve_for_read(reference: str, root: Path = Path(".")) -> Path:
    resolved = resolve_reference(reference)
    if "#" in resolved:
        resolved = resolved.split("#", 1)[0]
    root_resolved = root.resolve()
    path = (root_resolved / resolved).resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise ReferenceResolutionError("reference escapes repository root")
    return path


def resolve_for_write(reference: str, root: Path = Path(".")) -> Path:
    return resolve_for_read(reference, root)
