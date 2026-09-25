#!/usr/bin/env python3
"""Compare three recorded production runs; never infer missing Editor evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _sources(value: Any) -> list[str]:
    if isinstance(value, list):
        return [source for item in value for source in _sources(item)]
    if not isinstance(value, dict):
        return []
    if "resolved_path" in value:
        return [str(value["resolved_path"])]
    return [source for item in value.values() for source in _sources(item)]


def measure(arm: dict[str, Any], *, relevant_sources: set[str]) -> dict[str, Any]:
    manifest, result, evidence = arm["manifest"], arm["result"], arm["evidence"]
    if not isinstance(evidence, list) or not isinstance(manifest, dict) or not isinstance(result, dict):
        raise ValueError("each arm requires a Context Manifest, Runtime result, and durable Evidence records")
    if manifest["run_id"] != result["run_id"] or any(item.get("run_id") != result["run_id"] for item in evidence):
        raise ValueError("Context, Runtime, and Evidence must belong to the same run")
    if set(result.get("evidence_refs") or []) != {item.get("evidence_id") for item in evidence}:
        raise ValueError("every runtime evidence reference needs its durable Evidence record")
    view = manifest["materialized_context"]
    budget = manifest["budget_report"]
    if result.get("handoff", {}).get("context_id") != view["context_id"]:
        raise ValueError("Runtime handoff must use the measured Context identity")
    selected = set(_sources(view["selected_refs"]))
    specialist = view.get("specialist_context") or {}
    selected.update(f"specialist:{item['type']}:{item['key']}:{item['source']}" for item in specialist.get("items") or [])
    selected.update(f"binding:{key}" for key in view.get("resolved_bindings") or {})
    complete = bool(evidence) and all(item.get("verification_status") == "passed" and
        set(item.get("required_evidence") or []).issubset(set(item.get("observed_evidence") or []))
        for item in evidence)
    results = result.get("results") or []
    calls = sum(len(item.get("attempts") or []) for item in results)
    return {"run_id": result["run_id"], "selected_artifacts": budget["selected_artifacts"],
        "selected_bytes": budget["selected_utf8_bytes"], "estimated_tokens": budget["estimated_tokens"],
        "irrelevant_context_inclusion": sorted(selected - relevant_sources),
        "task_success": result.get("status") == "completed", "evidence_completeness": complete,
        "tool_calls": calls, "retries": sum(max(0, len(item.get("attempts") or []) - 1) for item in results),
        "budget_decision": budget["decision"]}


def compare(arms: dict[str, dict[str, Any]], relevant_sources: set[str]) -> dict[str, Any]:
    if set(arms) != {"A_existing", "B_naive", "C_filtered"}:
        raise ValueError("A_existing, B_naive and C_filtered recorded arms are required")
    if len({arm.get("task_id") for arm in arms.values()}) != 1 or not arms["A_existing"].get("task_id"):
        raise ValueError("all arms must share the same explicit task_id")
    contexts = {name: arm["manifest"]["materialized_context"].get("specialist_context") for name, arm in arms.items()}
    if contexts["A_existing"] is not None or not contexts["B_naive"] or not contexts["C_filtered"]:
        raise ValueError("A must omit specialist Context; B and C must include it")
    rows = {name: measure(arm, relevant_sources=relevant_sources) for name, arm in arms.items()}
    a, b, c = (rows[key] for key in ("A_existing", "B_naive", "C_filtered"))
    comparison_passed = (all(row["budget_decision"] == "within_budget" for row in (a, b, c))
        and c["selected_bytes"] < b["selected_bytes"]
        and len(c["irrelevant_context_inclusion"]) < len(b["irrelevant_context_inclusion"])
        and c["task_success"] and c["evidence_completeness"]
        and (not b["task_success"] or c["task_success"])
        and (not b["evidence_completeness"] or c["evidence_completeness"]))
    return {"arms": rows, "comparison_passed": comparison_passed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recorded_runs", type=Path, help="JSON with arms and task relevant_sources")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = json.loads(args.recorded_runs.read_text(encoding="utf-8"))
    report = compare(record["arms"], set(record["relevant_sources"]))
    output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if report["comparison_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
