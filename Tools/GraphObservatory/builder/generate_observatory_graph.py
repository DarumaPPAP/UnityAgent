"""Generate Graph Observatory artifacts."""

from pathlib import Path

from graph_builder import AgentGraph
from node_generators import build_architecture_graph, build_regression_graph
from readers import read_context, read_golden_tasks, read_harness


OUTPUT = Path("Artifacts/graph")


def generate() -> None:
    graph = AgentGraph()

    build_architecture_graph(
        graph,
        read_context(),
        read_harness(),
    )

    build_regression_graph(
        graph,
        read_golden_tasks(),
    )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "observatory.json").write_text(
        graph.to_json(),
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()
