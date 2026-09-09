"""Conservative conflict grouping for future source comparison."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
import re

from RAG.Contracts.models import RetrievalCandidate


def detect_conflicts(candidates: Iterable[RetrievalCandidate]) -> dict[str, list[str]]:
    """Group candidates with identical headings but different statements.

    This is a diagnostic only. It never discards a source or declares a newer
    source authoritative.
    """

    groups: dict[str, list[RetrievalCandidate]] = defaultdict(list)
    for candidate in candidates:
        key = re.sub(r"\s+", " ", candidate.heading.casefold()).strip()
        if key:
            groups[key].append(candidate)
    return {
        key: [candidate.candidate_id for candidate in values]
        for key, values in sorted(groups.items())
        if len({candidate.statement for candidate in values}) > 1
    }


__all__ = ["detect_conflicts"]
