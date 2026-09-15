"""Pure semantic continuation decisions.

This module never owns process retry, timeout, cancellation, turn/cost ceilings,
quota/lease accounting, durable persistence, tool execution, or route selection.
"""
from __future__ import annotations

from typing import Any

DECISIONS = frozenset({"continue", "replan", "exit", "blocked"})
FORBIDDEN_CONTROL_KEYS = frozenset(
    {
        "timeout_seconds",
        "hard_retry_ceiling",
        "maximum_retry_attempts",
        "max_turns",
        "cost_ceiling",
        "quota",
        "lease",
        "process_cleanup",
        "cancel_token",
        "retry_budget",
    }
)


def _outcomes(loop: dict[str, Any], key: str) -> tuple[str, ...]:
    values = loop.get(key) or []
    if not isinstance(values, list):
        raise ValueError(f"{key} must be a list")
    normalized = tuple(str(item) for item in values)
    if any(not item for item in normalized):
        raise ValueError(f"{key} contains an empty outcome")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{key} contains duplicate outcomes")
    return normalized


def validate_loop_definition(loop: dict[str, Any]) -> None:
    if not isinstance(loop, dict):
        raise ValueError("semantic loop definition must be an object")

    forbidden = sorted(FORBIDDEN_CONTROL_KEYS & set(loop))
    if forbidden:
        raise ValueError(
            "semantic loop contains Runtime/Persistence control fields: "
            + ", ".join(forbidden)
        )

    continue_on = set(_outcomes(loop, "continue_on"))
    replan_on = set(_outcomes(loop, "replan_on"))
    exit_on = set(_outcomes(loop, "exit_on"))

    overlap = (continue_on & replan_on) | (continue_on & exit_on) | (replan_on & exit_on)
    if overlap:
        raise ValueError(
            "semantic loop outcome sets must be disjoint: " + ", ".join(sorted(overlap))
        )


def decide_semantic_loop(
    loop: dict[str, Any],
    *,
    outcome: str,
    semantic_attempt: int,
    progress_marker: str | None,
    progress_made: bool = True,
    blocked: bool = False,
) -> dict[str, Any]:
    """Return one semantic decision without executing or persisting anything."""
    validate_loop_definition(loop)
    if semantic_attempt < 0:
        raise ValueError("semantic_attempt must not be negative")

    loop_id = str(loop.get("id") or "anonymous-loop")
    outcome_value = str(outcome or "")
    continue_on = set(_outcomes(loop, "continue_on"))
    replan_on = set(_outcomes(loop, "replan_on"))
    exit_on = set(_outcomes(loop, "exit_on"))

    if blocked:
        decision = "blocked"
        reason = "semantic blocker requires external resolution"
    elif outcome_value in exit_on:
        decision = "exit"
        reason = "semantic exit condition satisfied"
    elif outcome_value in replan_on:
        decision = "replan"
        reason = "semantic strategy must change"
    elif outcome_value in continue_on:
        if not progress_made:
            decision = "replan"
            reason = "semantic continuation made no progress"
        else:
            decision = "continue"
            reason = "bounded semantic continuation"
    else:
        decision = "blocked"
        reason = "outcome is not declared by semantic loop"

    next_attempt = semantic_attempt + (1 if decision in {"continue", "replan"} else 0)
    return {
        "schema_version": "1.0",
        "loop_id": loop_id,
        "outcome": outcome_value,
        "decision": decision,
        "semantic_attempt": next_attempt,
        "progress_marker": progress_marker,
        "replan_reason": reason if decision == "replan" else None,
        "reason": reason,
    }
