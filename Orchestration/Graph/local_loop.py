"""Semantic Local Loop decisions. Hard timeout/retry/turn/cost ceilings never belong here."""
from __future__ import annotations
from typing import Any

FORBIDDEN_LIMIT_KEYS = {"timeout_seconds", "hard_retry_ceiling", "max_turns", "cost_ceiling", "quota", "lease"}


def decide_local_loop(loop: dict[str, Any], *, outcome: str, semantic_attempt: int, progress_marker: str | None, progress_made: bool = True, blocked: bool = False) -> dict[str, Any]:
    if FORBIDDEN_LIMIT_KEYS & set(loop):
        raise ValueError("Local Loop contains Runtime/Persistence control fields")
    if semantic_attempt < 0:
        raise ValueError("semantic_attempt must not be negative")
    if blocked:
        decision = "blocked"
        reason = "semantic blocker requires external resolution"
    elif outcome in (loop.get("exit_on") or []):
        decision = "exit"
        reason = "Local Loop exit condition satisfied"
    elif outcome in (loop.get("replan_on") or []):
        decision = "replan"
        reason = "semantic strategy must change"
    elif outcome in (loop.get("continue_on") or []):
        if not progress_made:
            decision = "replan"
            reason = "continuation made no semantic progress"
        else:
            decision = "continue"
            reason = "bounded semantic continuation"
    else:
        decision = "blocked"
        reason = "outcome is not declared by Local Loop"
    return {"decision": decision, "semantic_attempt": semantic_attempt + (1 if decision in {"continue", "replan"} else 0), "progress_marker": progress_marker, "replan_reason": reason if decision == "replan" else None, "reason": reason}
