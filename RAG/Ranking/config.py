"""Load versioned ranking configuration without hardcoding final weights."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from RAG.Ranking.rrf import RRFConfig


def load_ranking_config(path: str | Path) -> tuple[RRFConfig, dict[str, Any]]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict) or value.get("kind") != "rag_ranking_config":
        raise ValueError("invalid RAG ranking config")
    rrf = RRFConfig.from_mapping(value.get("rrf") or {})
    reranker = value.get("reranker") or {}
    if not isinstance(reranker, dict):
        raise ValueError("ranking reranker config must be an object")
    return rrf, {
        "algorithm": str(value.get("algorithm") or "rrf"),
        "candidate_k": int(value.get("candidate_k", 24)),
        "top_k": int(value.get("top_k", 8)),
        "reranker": dict(reranker),
    }


__all__ = ["load_ranking_config"]
