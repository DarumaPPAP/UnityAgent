"""Reciprocal Rank Fusion with deterministic tie handling."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from RAG.Contracts.models import RetrievalCandidate


@dataclass(frozen=True)
class RRFConfig:
    """Versioned RRF configuration kept outside backend-specific code."""

    k: int = 60
    weights: Mapping[str, float] = field(default_factory=dict)
    revision: str = "rrf-v2"

    def __post_init__(self) -> None:
        if int(self.k) <= 0:
            raise ValueError("RRF k must be positive")
        normalized = {str(name): float(weight) for name, weight in dict(self.weights).items()}
        if any(weight < 0 for weight in normalized.values()):
            raise ValueError("RRF weights must be non-negative")
        if normalized and not any(weight > 0 for weight in normalized.values()):
            raise ValueError("at least one RRF weight must be positive")
        if not str(self.revision).strip():
            raise ValueError("RRF revision is required")
        object.__setattr__(self, "weights", normalized)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object] | None) -> "RRFConfig":
        data = dict(value or {})
        weights = data.get("weights") or {}
        if not isinstance(weights, Mapping):
            raise ValueError("RRF weights must be a mapping")
        return cls(
            k=int(data.get("k", data.get("rrf_k", 60))),
            weights={str(name): float(weight) for name, weight in weights.items()},
            revision=str(data.get("revision", "rrf-v2")),
        )

    def to_dict(self) -> dict[str, object]:
        return {"k": int(self.k), "weights": dict(self.weights), "revision": self.revision}


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Iterable[RetrievalCandidate]] | Sequence[Iterable[RetrievalCandidate]],
    *,
    weights: Mapping[str, float] | None = None,
    k: int = 60,
    config: RRFConfig | None = None,
    limit: int | None = None,
) -> list[RetrievalCandidate]:
    """Fuse ranked lists without losing the original candidate objects.

    Candidate identity is the source-qualified ``source_ref`` when available. This
    prevents identical document ids in two sources from being collapsed together.
    """

    effective_k = int(config.k) if config is not None else int(k)
    effective_weights = config.weights if config is not None else (weights or {})
    if effective_k <= 0:
        raise ValueError("RRF k must be positive")
    lists = list(ranked_lists.items()) if isinstance(ranked_lists, Mapping) else [
        (str(index), values) for index, values in enumerate(ranked_lists)
    ]
    by_key: dict[str, RetrievalCandidate] = {}
    fused: dict[str, float] = {}
    for list_name, ranked in lists:
        weight = float(effective_weights.get(str(list_name), 1.0))
        if weight < 0:
            raise ValueError("RRF weights must be non-negative")
        for rank, candidate in enumerate(ranked, start=1):
            key = candidate.source_ref or candidate.candidate_id
            by_key.setdefault(key, candidate)
            fused[key] = fused.get(key, 0.0) + weight / (effective_k + rank)
    for key, candidate in by_key.items():
        candidate.fusion_score = fused[key]
    result = sorted(
        by_key.values(),
        key=lambda item: (-item.fusion_score, item.candidate_id, item.source_ref),
    )
    return result if limit is None else result[: max(0, int(limit))]


def weighted_reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Iterable[RetrievalCandidate]] | Sequence[Iterable[RetrievalCandidate]],
    *,
    config: RRFConfig,
    limit: int | None = None,
) -> list[RetrievalCandidate]:
    """Explicit weighted-RRF entrypoint for config-driven ranking flows."""

    return reciprocal_rank_fusion(ranked_lists, config=config, limit=limit)
