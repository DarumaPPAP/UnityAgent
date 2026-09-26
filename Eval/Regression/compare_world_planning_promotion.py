"""Providerless World Planningの記録済みA/B/Cを比較する。昇格を自動決定しない。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from Runtime.ReferenceImplementation.world_planning import verify_world_plan


ARMS = {"A_unity_agent", "B_world_skill", "C_world_creator"}
QUALITY = {"plan_completeness", "dependency_quality", "open_decision_detection", "domain_hint_quality", "evidence_requirement_quality"}
COUNTS = {"hidden_decision_count", "unnecessary_work_packages", "token_usage"}
TRACE = {"clear", "partial", "unclear"}


def _review(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != QUALITY | COUNTS | {"goal_preservation", "trace_clarity"}:
        raise ValueError("each arm requires exact World Planning review metrics")
    if type(value["goal_preservation"]) is not bool or any(type(value[key]) is not int or not 0 <= value[key] <= 4 for key in QUALITY) or any(type(value[key]) is not int or value[key] < 0 for key in COUNTS) or value["trace_clarity"] not in TRACE:
        raise ValueError("World Planning review metrics are invalid")
    return value


def compare_world_planning(arms: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(arms) != ARMS:
        raise ValueError("A_unity_agent, B_world_skill, and C_world_creator arms are required")
    task_ids = {arm.get("task_id") for arm in arms.values()}
    run_kinds = {arm.get("run_kind") for arm in arms.values()}
    if len(task_ids) != 1 or not next(iter(task_ids)) or len(run_kinds) != 1 or next(iter(run_kinds)) not in {"fixture", "recorded_planning"}:
        raise ValueError("all arms require the same task_id and planning run kind")
    views = {name: arm["manifest"]["materialized_context"] for name, arm in arms.items()}
    if views["A_unity_agent"].get("specialist_context") is not None or views["B_world_skill"].get("specialist_context") is not None:
        raise ValueError("A and B must not carry Specialist Context")
    skill = views["B_world_skill"].get("selected_refs", {}).get("skill")
    if not isinstance(skill, dict) or not str(skill.get("resolved_path", "")).endswith("/SKILL.md"):
        raise ValueError("B requires an explicit World Planning Skill")
    candidate = arms["C_world_creator"]
    contract = verify_world_plan(candidate["manifest"], candidate["result"])
    rows: dict[str, dict[str, Any]] = {}
    for name, arm in arms.items():
        view = views[name]
        budget = arm["manifest"].get("budget_report")
        if not isinstance(budget, dict) or budget.get("decision") != "within_budget" or type(budget.get("selected_utf8_bytes")) is not int or budget["selected_utf8_bytes"] < 0:
            raise ValueError("each arm requires measured within-budget Context usage")
        plan = arm["result"].get("world_plan")
        if not isinstance(plan, dict):
            raise ValueError("each arm requires a recorded World Plan")
        rows[name] = {**_review(arm.get("review")), "context_bytes": budget["selected_utf8_bytes"], "work_package_count": len(plan.get("work_packages") or []), "context_id": view["context_id"]}
    return {"task_id": next(iter(task_ids)), "run_kind": next(iter(run_kinds)), "arms": rows, "candidate_contract_verified": contract["status"] == "fixture_contract_verified", "candidate_context_binding": "verified", "promotion_decision": "requires_human_review", "winner": None, "runtime_evaluation": "NOT_EVALUATED_RUNTIME"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recorded_runs", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = json.loads(args.recorded_runs.read_text(encoding="utf-8"))
    report = compare_world_planning(record["arms"])
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
