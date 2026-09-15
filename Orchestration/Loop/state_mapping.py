"""Project semantic loop decisions into Persistence contracts without persisting them."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

VALID_DECISIONS = frozenset({"continue", "replan", "exit", "blocked"})


def _now(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat()


def loop_control_state_patch(
    *,
    run_id: str,
    loop_id: str,
    semantic_attempt: int,
    progress_marker: str | None,
    decision: str,
    replan_reason: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    if decision not in VALID_DECISIONS:
        raise ValueError("invalid semantic loop decision")
    if semantic_attempt < 0:
        raise ValueError("semantic_attempt must not be negative")
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "loop_id": loop_id,
        "semantic_attempt": semantic_attempt,
        "progress_marker": progress_marker,
        "decision": decision,
        "replan_reason": replan_reason,
        "updated_at": _now(updated_at),
    }
