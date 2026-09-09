"""Read-only evidence summary helper for MyResourceCenter adapter tests."""

from __future__ import annotations

from typing import Any


def evidence_summary(chunk: dict[str, Any]) -> str:
    """Return the indexed summary; never fetches or copies an original document."""

    return str(chunk.get("summary") or "").strip()


__all__ = ["evidence_summary"]
