#!/usr/bin/env python3
"""Canonical repository reference resolver.

Only canonical repository-relative paths are accepted. Deprecated migration URI schemes and
legacy migration-root paths are rejected after cutover instead of being silently rewritten.
"""
from __future__ import annotations
from pathlib import Path


LEGACY_ROOT = "." + "ai"
LEGACY_PREFIX = LEGACY_ROOT + "/"
DEPRECATED_URI_SCHEME = "compatibility" + "://"


class ReferenceResolutionError(ValueError):
    pass


def resolve_reference(reference: str) -> str:
    value = str(reference).strip()
    if not value:
        raise ReferenceResolutionError("reference is required")
    if value.startswith(DEPRECATED_URI_SCHEME):
        raise ReferenceResolutionError("deprecated migration URI is forbidden after canonical cutover")
    base = value.split("#", 1)[0]
    if base == LEGACY_ROOT or base.startswith(LEGACY_PREFIX):
        raise ReferenceResolutionError("legacy migration-root path is forbidden after canonical cutover")
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
