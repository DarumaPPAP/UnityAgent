"""Graph Observatory foundation and compatibility contract tests."""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "Tools" / "GraphObservatory" / "builder"
PROJECTION = ROOT / "Tools" / "GraphObservatory" / "projection"
for path in (str(BUILDER), str(PROJECTION)):
    if path not in sys.path:
        sys.path.insert(0, path)


class GraphObservatoryFoundationContractTests(unittest.TestCase):
    @staticmethod
    def _defined_module_functions(path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def test_graph_model_exposes_metadata_and_json_apis(self) -> None:
        from graph_builder import AgentGraph

        graph = AgentGraph()
        self.assertTrue(hasattr(graph, "add_metadata"))
        self.assertTrue(hasattr(graph, "to_json"))

    def test_node_generator_matches_graph_node_contract(self) -> None:
        from graph_builder import AgentGraph
        from node_generators import build_architecture_graph

        build_architecture_graph(AgentGraph(), {"routes": {}}, {"gates": {}})

    def test_observatory_entrypoint_imports_canonical_reader_api(self) -> None:
        entrypoint = ROOT / "Tools/GraphObservatory/builder/generate_observatory_graph.py"
        readers = ROOT / "Tools/GraphObservatory/builder/readers.py"
        tree = ast.parse(entrypoint.read_text(encoding="utf-8"))
        imported = {
            alias.name for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "readers"
            for alias in node.names
        }
        self.assertTrue(imported.issubset(self._defined_module_functions(readers)))

    def test_projection_runner_imports_all_projection_builders(self) -> None:
        runner = ROOT / "Tools/GraphObservatory/projection/projection_runner.py"
        tree = ast.parse(runner.read_text(encoding="utf-8"))
        modules = {
            node.module: {alias.name for alias in node.names}
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module in {
                "context_projection", "harness_projection", "execution_projection", "regression_projection",
            }
        }
        for module, imported in modules.items():
            self.assertTrue(imported.issubset(self._defined_module_functions(PROJECTION / f"{module}.py")), module)

    def test_graph_metadata_matches_schema_requirements(self) -> None:
        from graph_builder import AgentGraph

        schema = json.loads((ROOT / "Tools/GraphObservatory/schema/graph.schema.json").read_text(encoding="utf-8"))
        required = set(schema["properties"]["metadata"]["required"])
        self.assertTrue(required.issubset(AgentGraph().to_dict()["metadata"].keys()))

    def test_aggregate_validator_exposes_graph_observatory_validation(self) -> None:
        validator = (ROOT / "Tools/validate_all.py").read_text(encoding="utf-8")
        self.assertIn("GraphObservatory", validator)
        self.assertIn("graph.schema.json", validator)
