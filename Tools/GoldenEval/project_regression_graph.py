#!/usr/bin/env python3
"""Project Golden Tasks and optional candidate results into a Regression Graph."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from run_golden_evals import infer_failures

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
DEFAULT_OUTPUT = ROOT / "Artifacts" / "GoldenEval" / "regression-graph.yaml"


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def node_id(kind: str, value: str) -> str:
    return f"{kind}:{value}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", help="Optional candidate result YAML")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    suite = load_yaml(CASES_PATH)
    cases = {case["id"]: case for case in suite.get("cases", []) or []}
    result_map = {}
    if args.results:
        result_doc = load_yaml(Path(args.results))
        result_map = {str(item.get("task_id")): item for item in result_doc.get("results", []) or []}

    nodes: list[dict] = []
    edges: list[dict] = []
    emitted: set[str] = set()

    def add_node(node: dict) -> None:
        if node["id"] not in emitted:
            nodes.append(node)
            emitted.add(node["id"])

    for task_id, case in cases.items():
        golden_id = node_id("golden_task", task_id)
        add_node({"id": golden_id, "type": "golden_task", "label": task_id, "category": case.get("category")})

        route = case.get("expectation", {}).get("route")
        if route:
            route_id = node_id("route", str(route))
            add_node({"id": route_id, "type": "route", "label": str(route)})
            edges.append({"source": golden_id, "target": route_id, "type": "expects"})

        for grader in case.get("graders", []) or []:
            grader_name = str(grader.get("id"))
            grader_id = node_id("grader", grader_name)
            add_node({"id": grader_id, "type": "grader", "label": grader_name, "grader_type": grader.get("type")})
            edges.append({"source": golden_id, "target": grader_id, "type": "evaluated_by"})

        result = result_map.get(task_id)
        if result is None:
            continue
        attempt_count = max(1, int(result.get("attempt_count", 1)))
        attempt_id = node_id("attempt", f"{task_id}:{attempt_count}")
        add_node({"id": attempt_id, "type": "attempt", "label": f"{task_id} attempt {attempt_count}"})
        edges.append({"source": golden_id, "target": attempt_id, "type": "compares_to"})

        failures = infer_failures(case, result)
        status = "passed" if not failures else "failed"
        regression_id = node_id("regression_result", task_id)
        add_node({
            "id": regression_id,
            "type": "regression_result",
            "label": status,
            "status": status,
            "failures": failures,
        })
        edges.append({"source": attempt_id, "target": regression_id, "type": "produces_regression_result"})

    graph = {
        "schema_version": "1.0",
        "graph_kind": "regression",
        "source": "Tests/GoldenTasks/cases.yaml",
        "nodes": nodes,
        "edges": edges,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(graph, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Regression Graph built: {output} ({len(nodes)} nodes / {len(edges)} edges)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
