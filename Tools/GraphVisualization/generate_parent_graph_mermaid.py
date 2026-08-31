#!/usr/bin/env python3
"""Generate the GitHub-renderable Parent Graph Mermaid projection from canonical YAML."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = ROOT / "Orchestration/Definitions/development-parent-graph.yaml"
OUTPUT_PATH = ROOT / "docs/architecture/unityagent-flow.mmd"


def _escape(value: object) -> str:
    return str(value).replace('"', "'")


def _node_expression(node: dict, human_gate_nodes: set[str]) -> str:
    node_id = str(node["id"])
    label = f"{node_id}<br/>{node['owner']} / {node['kind']}"
    if node_id in human_gate_nodes:
        return f'        {node_id}{{"{_escape(label)}<br/>HUMAN GATE"}}'
    return f'        {node_id}["{_escape(label)}"]'


def render_mermaid(graph: dict) -> str:
    human_gate_nodes = {
        str(gate["node_id"])
        for gate in graph.get("gates", [])
        if gate.get("source") == "human"
    }

    lines = ["flowchart TD"]
    for subgraph in graph.get("subgraphs", []):
        subgraph_id = str(subgraph["id"])
        lines.append(f'    subgraph sg_{subgraph_id}["{_escape(subgraph_id)}"]')
        for node in subgraph.get("nodes", []):
            lines.append(_node_expression(node, human_gate_nodes))
        lines.append("    end")
        lines.append("")

    for edge in graph.get("edges", []):
        lines.append(
            f'    {edge["from"]} -->|"{_escape(edge["on"])}"| {edge["to"]}'
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail when the committed Mermaid projection is stale.")
    args = parser.parse_args()

    graph = yaml.safe_load(GRAPH_PATH.read_text(encoding="utf-8")) or {}
    rendered = render_mermaid(graph)

    if args.check:
        if not OUTPUT_PATH.is_file():
            print(f"Missing generated Mermaid diagram: {OUTPUT_PATH.relative_to(ROOT)}")
            return 1
        committed = OUTPUT_PATH.read_text(encoding="utf-8")
        if committed != rendered:
            print("Parent Graph Mermaid projection is stale.")
            print("Regenerate with: python Tools/GraphVisualization/generate_parent_graph_mermaid.py")
            return 1
        print("Parent Graph Mermaid projection is current.")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
