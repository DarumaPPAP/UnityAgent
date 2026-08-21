"""Graph Observatory export entry point."""

import json
from pathlib import Path

from graph_builder import AgentGraph
from readers import CanonicalReader


OUTPUT_DIR = Path("Artifacts/graph")


def export_graph(graph: AgentGraph, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(graph.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def export_from_repository(repository_root: str) -> None:
    """Build graph artifacts from canonical UnityAgent sources.

    YAML remains the source of truth. Generated graph artifacts are views only.
    """

    reader = CanonicalReader(repository_root)
    graph = AgentGraph()

    contract = reader.read_graph_contract()
    graph.add_metadata("source", "canonical-yaml")
    graph.add_metadata("contract_nodes", len(contract))

    export_graph(graph, OUTPUT_DIR / "architecture.json")


if __name__ == "__main__":
    export_from_repository(".")
