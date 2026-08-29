"""Health-check Nodes depend on a Runtime health port; they contain no OS/tool implementation."""
from __future__ import annotations
from typing import Any, Protocol


class RuntimeHealthPort(Protocol):
    def probe(self, request: dict[str, Any]) -> dict[str, Any]: ...


def execute_health_check(port: RuntimeHealthPort, request: dict[str, Any], *, required: bool) -> dict[str, Any]:
    result = port.probe(request)
    status = result.get("status")
    if status not in {"healthy", "degraded", "unavailable", "failed"}:
        raise ValueError("Runtime health port returned invalid status")
    if status == "healthy":
        consequence = "continue"
    elif status == "degraded":
        consequence = "replan" if required else "continue"
    elif status == "unavailable":
        consequence = "blocked" if required else "replan"
    else:
        consequence = "blocked"
    return {"health_result": result, "consequence": consequence}
