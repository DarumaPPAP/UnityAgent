"""Semantic consequence of already-observed gate/health evidence. Enforcement remains Runtime/Policy."""
from __future__ import annotations


def route_gate(*, requirement: str, status: str) -> str:
    if requirement not in {"required", "conditional", "informational", "not_applicable"}:
        raise ValueError("invalid gate requirement")
    if status not in {"passed", "failed", "unavailable"}:
        raise ValueError("invalid gate status")
    if requirement in {"informational", "not_applicable"}:
        return "continue"
    if status == "passed":
        return "continue"
    if status == "unavailable":
        return "replan"
    return "blocked"
