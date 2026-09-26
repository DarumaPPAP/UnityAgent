"""実測したA/B/C Specialist Pilotを比較する。昇格判断は自動化しない。"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from Eval.Regression.compare_specialist_three_way import _sources, measure


ARMS = {"A_unity_agent", "B_skill_tool", "C_specialist"}
REVIEW_COUNTS = {"wrong_assumptions", "tool_selection_errors", "approval_violations", "unsupported_claims"}
TRACE_STATES = {"clear", "partial", "unclear"}


def _review(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != (REVIEW_COUNTS | {"trace_legibility", "latency_ms"}):
        raise ValueError("each arm requires an exact human review record")
    if any(type(value[key]) is not int or value[key] < 0 for key in REVIEW_COUNTS):
        raise ValueError("review counts must be nonnegative integers")
    if value["trace_legibility"] not in TRACE_STATES:
        raise ValueError("review trace_legibility is invalid")
    latency = value["latency_ms"]
    if latency is not None and (type(latency) not in {int, float} or not math.isfinite(latency) or latency < 0):
        raise ValueError("review latency_ms must be nonnegative or unavailable")
    return value


def compare_promotion(arms: dict[str, dict[str, Any]], relevant_sources: set[str]) -> dict[str, Any]:
    if set(arms) != ARMS:
        raise ValueError("A_unity_agent, B_skill_tool, and C_specialist recorded arms are required")
    task_ids = {arm.get("task_id") for arm in arms.values()}
    if len(task_ids) != 1 or not next(iter(task_ids)):
        raise ValueError("all arms require the same explicit task_id")
    contexts = {name: arm["manifest"]["materialized_context"] for name, arm in arms.items()}
    if contexts["A_unity_agent"].get("specialist_context") is not None or contexts["B_skill_tool"].get("specialist_context") is not None or not contexts["C_specialist"].get("specialist_context"):
        raise ValueError("only C_specialist may carry Specialist Context")
    skill_sources = _sources(contexts["B_skill_tool"].get("selected_refs", {}).get("skill"))
    if not any(source.endswith("/SKILL.md") for source in skill_sources):
        raise ValueError("B_skill_tool requires a selected Skill")

    rows = {}
    for name, arm in arms.items():
        rows[name] = {**measure(arm, relevant_sources=relevant_sources), **_review(arm.get("review"))}
    if rows["B_skill_tool"]["tool_calls"] < 1:
        raise ValueError("B_skill_tool requires a recorded deterministic Tool call")
    candidate = rows["C_specialist"]
    if not candidate["receipt_integrity"]:
        raise ValueError("C_specialist Context Receipt is not verified")
    candidate_valid = candidate["task_success"] and candidate["evidence_completeness"] and candidate["required_context_complete"] and candidate["approval_violations"] == 0 and candidate["unsupported_claims"] == 0
    return {"task_id": next(iter(task_ids)), "arms": rows, "candidate_evidence_valid": candidate_valid, "promotion_decision": "requires_human_review"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recorded_runs", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = json.loads(args.recorded_runs.read_text(encoding="utf-8"))
    report = compare_promotion(record["arms"], set(record["relevant_sources"]))
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
