"""MyUnityMCP instance binding helpers.

This module observes/binds structured connector facts only. It does not select a
provider, install MCP components, or relax project binding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from Runtime.Tooling.Environment.project_identity import same_project_root

TriState = bool | str


@dataclass(frozen=True)
class MyUnityMcpInstanceObservation:
    instance_id: str
    reachable: TriState
    project_root: str | None
    enabled_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class MyUnityMcpBinding:
    reachable: TriState
    available: TriState
    project_bound: TriState
    binding_status: str
    bound_instance_id: str | None
    enabled_tools: tuple[str, ...] = ()


def bind_myunitymcp_instance(
    project_root: str,
    instances: Sequence[MyUnityMcpInstanceObservation] | None,
) -> MyUnityMcpBinding:
    """Bind exactly one reachable MyUnityMCP instance to the requested project."""
    if instances is None:
        return MyUnityMcpBinding("unknown", "unknown", "unknown", "unknown", None)

    if not instances:
        return MyUnityMcpBinding(False, False, False, "unbound", None)

    reachable = [item for item in instances if item.reachable is True]
    has_unknown = any(item.reachable == "unknown" for item in instances)

    if not reachable:
        if has_unknown:
            return MyUnityMcpBinding("unknown", "unknown", "unknown", "unknown", None)
        return MyUnityMcpBinding(False, False, False, "unbound", None)

    matching = [
        item
        for item in reachable
        if item.project_root
        and same_project_root(item.project_root, project_root)
    ]

    if len(matching) == 1:
        item = matching[0]
        return MyUnityMcpBinding(
            True,
            True,
            True,
            "bound",
            item.instance_id,
            tuple(sorted(set(item.enabled_tools))),
        )

    if len(matching) > 1:
        return MyUnityMcpBinding(True, False, False, "ambiguous_binding", None)

    return MyUnityMcpBinding(True, False, False, "unbound", None)
