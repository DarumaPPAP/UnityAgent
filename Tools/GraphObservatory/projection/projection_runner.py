"""Phase 8.8 Projection Runner.

Coordinates read-only graph projection adapters.
Canonical YAML remains the source of truth.
"""

from pathlib import Path

from context_projection import build_context_graph
from harness_projection import build_harness_graph
from execution_projection import build_execution_graph
from regression_projection import build_regression_graph


def build_projection_bundle(output_dir: Path, sources: dict) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    graphs = {
        "context": build_context_graph(sources.get("context", {})),
        "harness": build_harness_graph(sources.get("harness", {})),
        "execution": build_execution_graph(sources.get("execution", {})),
        "regression": build_regression_graph(sources.get("regression", {})),
    }

    for name, graph in graphs.items():
        (output_dir / f"{name}.json").write_text(
            graph.to_json(),
            encoding="utf-8",
        )

    return graphs
