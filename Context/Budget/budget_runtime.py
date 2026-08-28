#!/usr/bin/env python3
from __future__ import annotations
import math
from pathlib import Path
from typing import Any
import yaml

CONTRACT = Path("Context/Budget/context-budget.yaml")

def load_contract(root: Path = Path(".")) -> dict[str, Any]:
    data = yaml.safe_load((root / CONTRACT).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Context budget contract must be a mapping")
    return data

def estimate_tokens(selected_utf8_bytes: int, divisor: int = 3) -> int:
    return 0 if selected_utf8_bytes <= 0 else int(math.ceil(selected_utf8_bytes / divisor))

def evaluate(
    route_id: str,
    selected_sizes: list[int],
    *,
    missing_observations: list[str] | None = None,
    external_fetches: int = 0,
    context_includes: int = 0,
    expansion_hops: int = 0,
    root: Path = Path("."),
) -> dict[str, Any]:
    contract = load_contract(root)
    profile_id = (contract.get("route_profiles") or {}).get(route_id, "standard")
    profile = (contract.get("profiles") or {}).get(profile_id)
    if not isinstance(profile, dict):
        raise ValueError(f"Unknown context budget profile: {profile_id}")
    retrieval = profile["retrieval"]
    context = profile["context"]
    total = sum(selected_sizes)
    divisor = int(contract["estimator"]["utf8_bytes_per_estimated_token"])
    tokens = estimate_tokens(total, divisor)
    missing = sorted(set(missing_observations or []))
    blocked = (
        len(selected_sizes) > int(retrieval["max_artifacts"])
        or total > int(retrieval["max_selected_utf8_bytes"])
        or external_fetches > int(retrieval["max_external_fetches"])
        or context_includes > int(retrieval["max_context_includes"])
        or expansion_hops > int(retrieval["max_expansion_hops"])
        or tokens > int(context["hard_estimated_tokens"])
    )
    if blocked:
        decision = "blocked"
    elif missing:
        decision = "unmeasured"
    elif tokens > int(context["soft_estimated_tokens"]):
        decision = "compression_required"
    else:
        decision = "within_budget"
    return {
        "profile": profile_id,
        "estimator": str(contract["estimator"]["id"]),
        "selected_artifacts": len(selected_sizes),
        "selected_utf8_bytes": total,
        "estimated_tokens": tokens,
        "missing_observations": missing,
        "decision": decision,
    }
