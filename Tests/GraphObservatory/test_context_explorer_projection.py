"""Context Explorer projection and provenance tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/GraphObservatory"))
from context_projection import build_context_graph  # noqa: E402
from validate_graph import validate_graph  # noqa: E402


class ContextExplorerProjectionTests(unittest.TestCase):
    def test_context_projection_is_valid_and_deterministic(self) -> None:
        first = build_context_graph(ROOT).to_json()
        second = build_context_graph(ROOT).to_json()
        self.assertEqual(first, second)
        self.assertEqual(validate_graph(build_context_graph(ROOT).to_dict()), [])

    def test_context_nodes_have_source_hash_and_provenance(self) -> None:
        for node in build_context_graph(ROOT).to_dict()["nodes"]:
            self.assertEqual(node["type"], "context")
            self.assertIn("source_hash", node["metadata"]["provenance"])
            self.assertIn("source_path", node["metadata"]["provenance"])
