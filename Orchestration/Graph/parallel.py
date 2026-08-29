"""Pure semantic parallel planning. Runtime decides how/if approved actions are actually dispatched."""
from __future__ import annotations
from typing import Any


def plan_parallel(nodes: list[dict[str, Any]]) -> list[list[str]]:
    groups: list[list[dict[str, Any]]] = []
    for node in nodes:
        if not node.get("parallel_safe", False):
            groups.append([node])
            continue
        write_set = set(node.get("write_set") or [])
        placed = False
        for group in groups:
            if all(item.get("parallel_safe", False) for item in group):
                occupied = {path for item in group for path in (item.get("write_set") or [])}
                if not (write_set & occupied):
                    group.append(node)
                    placed = True
                    break
        if not placed:
            groups.append([node])
    return [[str(item["id"]) for item in group] for group in groups]
