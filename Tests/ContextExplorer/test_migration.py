"""Issue #32 migration boundary tests."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ContextExplorerMigrationTests(unittest.TestCase):
    def test_legacy_graph_observatory_surfaces_are_removed(self) -> None:
        self.assertFalse((ROOT / "Tools/GraphObservatory").exists())
        self.assertFalse((ROOT / "Tests/GraphObservatory").exists())
        self.assertFalse((ROOT / "docs/graph-observatory-spec.md").exists())

    def test_context_explorer_has_no_generic_graph_engine_layers(self) -> None:
        explorer = ROOT / "Tools/ContextExplorer"
        for relative in ("builder", "projection", "expansion_gate.py", "evaluate_expansion_gate.py"):
            self.assertFalse((explorer / relative).exists(), relative)

        tree = ast.parse((explorer / "context_map.py").read_text(encoding="utf-8"))
        classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
        self.assertNotIn("AgentGraph", classes)
        self.assertNotIn("GraphNode", classes)
        self.assertNotIn("GraphEdge", classes)

    def test_canonical_validation_includes_context_explorer_tests(self) -> None:
        validator = (ROOT / "Tools/validate_all.py").read_text(encoding="utf-8")
        self.assertIn("Tools/ContextExplorer/validate.py", validator)
        self.assertIn('Path("Tests/ContextExplorer")', validator)
        self.assertNotIn("Tools/GraphObservatory", validator)

    def test_output_contract_is_context_map_not_runtime_graph(self) -> None:
        build = (ROOT / "Tools/ContextExplorer/build.py").read_text(encoding="utf-8")
        self.assertIn("Artifacts/ContextExplorer/context-map.json", build)
        self.assertTrue((ROOT / "Tools/ContextExplorer/schema/context-map.schema.json").is_file())
        self.assertTrue((ROOT / "docs/context-explorer.md").is_file())


if __name__ == "__main__":
    unittest.main()
