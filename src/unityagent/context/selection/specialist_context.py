"""Select attempt-scoped specialist observations without deciding a route or Provider."""
from __future__ import annotations

import re
from typing import Any

ALLOWED_CATEGORIES = {"project_fact", "project_decision", "platform_fact", "platform_decision", "task_fact"}
REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")


def observation_items(observations: list[dict[str, Any]], tags: list[str], attempt: int = 1) -> list[dict[str, Any]]:
    """Control Planeが永続検証した観測を、既存Selection/Budget対象のFactへ投影する。"""
    items = []
    for observation in observations:
        payload, record = observation["payload"], observation["record"]
        items.append({"category": "project_fact", "key": f"observation:{payload['capability']}",
            "value": {"capability": payload["capability"], "result": payload["result"], "environment": record["environment"], "target": record["target"], "observed_evidence": record["observed_evidence"], "interpretation": "untrusted_tool_observation_not_instruction"},
            "source": f"evidence:{record['evidence_id']}", "revision": observation["revision"], "tags": list(tags),
            "freshness": {"status": "current", "checked_at_attempt": attempt}, "observed_at_attempt": attempt, "required": True})
        # 観測Capabilityの既知の出力だけをFact化し、任意のTask/Decision注入は許可しない。
        result = payload["result"]
        facts = {}
        if payload["capability"] == "project.inspect" and isinstance(result.get("render_pipeline"), str) and result["render_pipeline"] not in {"", "unknown"}:
            facts["render_pipeline"] = result["render_pipeline"]
        if payload["capability"] == "source.read" and isinstance(result.get("path"), str) and result["path"] and isinstance(result.get("content"), str):
            facts["relevant_source"] = result["path"]
        for key, value in facts.items():
            items.append({**items[-1], "key": key, "value": value})
    return items


def select_items(items: list[dict[str, Any]], tags: set[str], required_keys: set[str], attempt: int) -> list[dict[str, Any]]:
    if attempt < 1 or not tags or any(not isinstance(tag, str) or not tag for tag in tags):
        raise ValueError("specialist tags and positive attempt are required")
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or item.get("category") not in ALLOWED_CATEGORIES:
            raise ValueError("unsupported specialist context category")
        category = item["category"]
        key = item.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("specialist context key is required")
        identifier = f"{category}:{key}"
        item_tags = item.get("tags")
        if not isinstance(item_tags, list) or not item_tags or any(not isinstance(tag, str) or not tag for tag in item_tags):
            raise ValueError("specialist context tags must be explicit")
        if not tags.intersection(item_tags):
            continue
        if identifier in seen:
            raise ValueError(f"duplicate specialist context: {identifier}")
        seen.add(identifier)
        source, revision = item.get("source"), item.get("revision")
        if not isinstance(source, str) or not source or not isinstance(revision, str) or not REVISION.fullmatch(revision):
            raise ValueError(f"specialist context requires source and sha256 revision: {identifier}")
        if category.endswith("decision") and not source.startswith(("user:", "project_policy:")):
            raise ValueError(f"specialist decision requires explicit authority: {identifier}")
        freshness = item.get("freshness")
        if not isinstance(freshness, dict) or freshness.get("status") not in {"current", "stale", "unknown"}:
            raise ValueError(f"invalid specialist freshness: {identifier}")
        checked = freshness.get("checked_at_attempt")
        if not isinstance(checked, int) or isinstance(checked, bool) or checked < 1 or checked > attempt:
            raise ValueError(f"invalid specialist checked_at_attempt: {identifier}")
        if freshness["status"] != "current" or checked != attempt:
            continue
        observed = item.get("observed_at_attempt")
        if category.endswith("fact"):
            if not isinstance(observed, int) or isinstance(observed, bool) or observed < 1 or observed > checked:
                raise ValueError(f"invalid specialist observed_at_attempt: {identifier}")
        if "value" not in item or item["value"] is None or item["value"] == "unknown":
            continue
        entry = {"type": category, "key": key, "value": item["value"], "source": source,
                 "revision": revision, "selected_reason": f"task tags: {', '.join(sorted(tags.intersection(item_tags)))}",
                 "compression": "none", "freshness": freshness.copy()}
        if category.endswith("fact"):
            entry["observed_at_attempt"] = observed
        selected.append(entry)
    missing = required_keys.difference({f"{entry['type']}:{entry['key']}" for entry in selected})
    missing.update(f"{item['category']}:{item['key']}" for item in items if isinstance(item, dict)
                   and item.get("required") is True and set(item.get("tags") or []).intersection(tags)
                   and f"{item['category']}:{item['key']}" not in {f"{entry['type']}:{entry['key']}" for entry in selected})
    if missing:
        raise ValueError(f"required specialist context unavailable: {sorted(missing)}")
    return selected
