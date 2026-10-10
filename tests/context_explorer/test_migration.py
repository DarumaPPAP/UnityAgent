"""Context Explorer migration and visualization boundary tests."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ContextExplorerMigrationTests(unittest.TestCase):
    def test_legacy_graph_observatory_surfaces_are_removed(self) -> None:
        self.assertFalse((ROOT / "tools/GraphObservatory").exists())
        self.assertFalse((ROOT / "tests/graph_observatory").exists())
        self.assertFalse((ROOT / "docs/graph-observatory-spec.md").exists())

    def test_context_explorer_has_no_generic_graph_engine_layers(self) -> None:
        explorer = ROOT / "tools/context_explorer"
        for relative in ("builder", "projection", "expansion_gate.py", "evaluate_expansion_gate.py"):
            self.assertFalse((explorer / relative).exists(), relative)

        tree = ast.parse((explorer / "context_map.py").read_text(encoding="utf-8"))
        classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
        self.assertNotIn("AgentGraph", classes)
        self.assertNotIn("GraphNode", classes)
        self.assertNotIn("GraphEdge", classes)

    def test_canonical_validation_includes_context_explorer_tests(self) -> None:
        validator = (ROOT / "tools/validate_all.py").read_text(encoding="utf-8")
        self.assertIn("tools/context_explorer/validate.py", validator)
        self.assertIn('Path("tests/context_explorer")', validator)
        self.assertNotIn("tools/GraphObservatory", validator)

    def test_output_contract_is_context_map_not_runtime_graph(self) -> None:
        build = (ROOT / "tools/context_explorer/build.py").read_text(encoding="utf-8")
        app = (ROOT / "tools/context_explorer/frontend/app.js").read_text(encoding="utf-8")
        html = (ROOT / "tools/context_explorer/frontend/index.html").read_text(encoding="utf-8")
        self.assertIn("Artifacts/ContextExplorer/context-map.json", build)
        self.assertIn("__CONTEXT_MAP__", build + app + html)
        self.assertNotIn("__CONTEXT_GRAPH__", build + app + html)
        self.assertNotIn("const graph =", app)
        self.assertTrue((ROOT / "tools/context_explorer/schema/context-map.schema.json").is_file())
        self.assertTrue((ROOT / "docs/context-explorer.md").is_file())

    def test_orchestration_graph_remains_separate_from_context_explorer(self) -> None:
        orchestration_graph = ROOT / "src/unityagent/orchestration/graph"
        self.assertTrue(orchestration_graph.is_dir())
        viewer_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "tools/context_explorer/context_map.py",
                ROOT / "tools/context_explorer/frontend/app.js",
            )
        )
        self.assertNotIn("unityagent.orchestration.graph", viewer_source)
        self.assertNotIn("src/unityagent/orchestration/graph", viewer_source)


if __name__ == "__main__":
    unittest.main()
