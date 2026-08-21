"""Phase 8 Graph Observatory artifact generation entry point.

Canonical YAML is the source of truth. This module only creates derived graph artifacts.
"""

from pathlib import Path
import json


def write_graph_artifact(graph: dict, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def generate_artifacts(graph: dict, output_dir: str) -> None:
    output = Path(output_dir)
    write_graph_artifact(graph, str(output / "observatory.json"))
    write_graph_artifact(graph, str(output / "architecture.json"))
    write_graph_artifact(graph, str(output / "execution.json"))
    write_graph_artifact(graph, str(output / "regression.json"))


if __name__ == "__main__":
    generate_artifacts(
        {"nodes": [], "edges": [], "metadata": {"generated_by": "GraphObservatory"}},
        "Artifacts/graph",
    )
