#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml

MAP_PATH = Path("Context/Compatibility/legacy-path-map.yaml")

class CompatibilityError(ValueError):
    pass

def _load(root: Path) -> dict[str, Any]:
    data = yaml.safe_load((root / MAP_PATH).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or data.get("writes_allowed") is not False:
        raise CompatibilityError("Phase 2 compatibility map must be read-only")
    return data

def resolve_reference(reference: str, root: Path = Path(".")) -> str:
    reference = str(reference).strip()
    data = _load(root)
    if reference.startswith("compatibility://"):
        key = reference[len("compatibility://"):]
        entry = (data.get("read_only_entries") or {}).get(key)
        if not isinstance(entry, dict) or not entry.get("path"):
            raise CompatibilityError(f"unknown compatibility key: {key}")
        return str(entry["path"])

    fragment = ""
    base = reference
    if "#" in reference:
        base, fragment = reference.split("#", 1)
        fragment = "#" + fragment

    rewrites = data.get("path_rewrites") or {}
    for old in sorted(rewrites, key=len, reverse=True):
        if base == old or (old.endswith("/") and base.startswith(old)):
            target = str(rewrites[old])
            if old.endswith("/"):
                target = target + base[len(old):]
            return target + fragment
    return reference

def resolve_for_read(reference: str, root: Path = Path(".")) -> Path:
    resolved = resolve_reference(reference, root)
    if "#" in resolved:
        resolved = resolved.split("#", 1)[0]
    path = (root / resolved).resolve()
    root_resolved = root.resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise CompatibilityError("reference escapes repository root")
    return path

def resolve_for_write(*_: object, **__: object) -> Path:
    raise CompatibilityError("legacy compatibility writes are forbidden")
