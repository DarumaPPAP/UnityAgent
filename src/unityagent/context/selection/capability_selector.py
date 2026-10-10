"""Select only the Context descriptions needed for requested capabilities."""
from __future__ import annotations
from unityagent.resources import resource_root

from pathlib import Path
from typing import Any

import yaml

ROOT = resource_root()
CATALOG_PATH = Path("src/unityagent/context/selection/tool-capability-catalog.yaml")


def select_capability_context(
    capability_ids: list[str],
    *,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    catalog = yaml.safe_load((root / CATALOG_PATH).read_text(encoding="utf-8")) or {}
    if not isinstance(catalog, dict):
        raise ValueError("capability context catalog must be a mapping")
    capabilities = catalog.get("capabilities") or {}

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for capability_id in capability_ids:
        if capability_id in seen:
            continue
        entry = capabilities.get(capability_id)
        if not isinstance(entry, dict):
            raise ValueError(f"unknown capability: {capability_id}")
        selected.append(
            {
                "capability": capability_id,
                "description": str(entry["description"]),
                "context_tags": [str(item) for item in entry.get("context_tags") or []],
                "mutation": entry.get("mutation") is True,
            }
        )
        seen.add(capability_id)
    return selected
