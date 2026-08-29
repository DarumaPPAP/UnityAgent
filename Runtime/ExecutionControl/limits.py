"""Hard execution limits. Semantic replan/retry belongs to Orchestration."""
from __future__ import annotations
from dataclasses import dataclass


class RuntimeLimitError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ExecutionLimits:
    timeout_seconds: float
    hard_retry_ceiling: int
    max_turns: int
    cost_ceiling: float | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if self.hard_retry_ceiling < 0:
            raise ValueError("hard_retry_ceiling must be >= 0")
        if self.max_turns <= 0:
            raise ValueError("max_turns must be > 0")
        if self.cost_ceiling is not None and self.cost_ceiling < 0:
            raise ValueError("cost_ceiling must be >= 0")


class ExecutionLimitTracker:
    def __init__(self, limits: ExecutionLimits) -> None:
        self.limits = limits
        self.attempts = 0
        self.turns = 0
        self.cost = 0.0

    def begin_attempt(self) -> None:
        if self.attempts >= self.limits.hard_retry_ceiling + 1:
            raise RuntimeLimitError("hard_retry_ceiling", "hard retry ceiling reached")
        self.attempts += 1

    def consume_turn(self) -> None:
        if self.turns >= self.limits.max_turns:
            raise RuntimeLimitError("max_turns", "hard turn ceiling reached")
        self.turns += 1

    def add_cost(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("cost delta must be >= 0")
        candidate = self.cost + amount
        if self.limits.cost_ceiling is not None and candidate > self.limits.cost_ceiling:
            raise RuntimeLimitError("cost_ceiling", "hard cost ceiling reached")
        self.cost = candidate
