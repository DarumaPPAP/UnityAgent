"""Graph Observatory export entry point."""

import json
from pathlib import Path

from graph_builder import AgentGraph


OUTPUT_DIR = Path("Artifacts/graph")


def export_graph(graph: AgentGraph, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(graph.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    export_graph(AgentGraph(), OUTPUT_DIR / "architecture.json")
