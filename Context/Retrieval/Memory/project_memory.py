"""Read-only bounded projection of durable Persistence Memory for Context."""
from __future__ import annotations
import hashlib
import json
import re
from typing import Any

from Persistence.Memory.memory_store import MemoryStore

TOKEN_RE = re.compile(r"[A-Za-z0-9_./:+-]{2,}")
LAYER_WEIGHT = {"atom": 2.0, "scenario": 3.0, "reusable_candidate": 4.0}


def _tokens(value: Any) -> set[str]:
    text = " ".join(map(str, value)) if isinstance(value, list) else str(value or "")
    return {token.lower() for token in TOKEN_RE.findall(text)}


def _score(record: dict[str, Any], query: set[str], repository, unity_version, platform) -> float:
    searchable = set()
    for field in ("statement", "applicability", "limits", "provenance", "tags", "repository", "unity_version", "platform"):
        searchable |= _tokens(record.get(field))
    score = len(query & searchable) * 10.0 + LAYER_WEIGHT.get(record.get("layer"), 1.0)
    for field, wanted, bonus in (("repository", repository, 4.0), ("unity_version", unity_version, 2.0), ("platform", platform, 2.0)):
        if wanted and str(record.get(field) or "").lower() == str(wanted).lower():
            score += bonus
    if record.get("confidence") == "verified":
        score += 1.0
    return score


def retrieve_projections(
    *, store_root, query: str, execution_profile: str, selected_at: str,
    repository: str | None = None, unity_version: str | None = None, platform: str | None = None,
    max_items: int = 8, max_chars: int = 6000,
) -> dict[str, Any]:
    if not 1 <= max_items <= 20:
        raise ValueError("max_items must be 1..20")
    if not 256 <= max_chars <= 12000:
        raise ValueError("max_chars must be 256..12000")
    store = MemoryStore(store_root)
    query_tokens = _tokens(query)
    ranked = []
    for record in store.list_accessible(execution_profile):
        score = _score(record, query_tokens, repository, unity_version, platform)
        base = LAYER_WEIGHT.get(record.get("layer"), 1.0) + (1.0 if record.get("confidence") == "verified" else 0.0)
        if query_tokens and score <= base:
            continue
        ranked.append((score, record))
    ranked.sort(key=lambda pair: (pair[0], pair[1].get("updated_at", ""), pair[1]["memory_id"]), reverse=True)

    items, characters, truncated = [], 0, False
    for score, record in ranked:
        if len(items) >= max_items:
            truncated = True
            break
        projection = {
            "schema_version": "1.0",
            "projection_id": "memory-projection-" + hashlib.sha256(f"{record['memory_id']}:{selected_at}".encode()).hexdigest()[:16],
            "memory_id": record["memory_id"],
            "source_evidence_refs": list(record["source_evidence_refs"]),
            "projection_ref": f"persistence://memory/{record['memory_id']}",
            "selected_at": selected_at,
        }
        item = {
            "projection": projection,
            "statement": record["statement"],
            "confidence": record["confidence"],
            "applicability": list(record.get("applicability") or []),
            "limits": list(record.get("limits") or []),
            "score": round(score, 3),
        }
        size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
        if items and characters + size > max_chars:
            truncated = True
            break
        if not items and size > max_chars:
            item["statement"] = item["statement"][: max(64, max_chars // 2)]
            size = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
            truncated = True
        items.append(item)
        characters += size
    return {
        "query": query,
        "execution_profile": execution_profile,
        "items": items,
        "item_count": len(items),
        "characters": characters,
        "truncated": truncated,
        "raw_content_included": False,
        "durable_memory_owner": "Persistence/Memory",
    }
