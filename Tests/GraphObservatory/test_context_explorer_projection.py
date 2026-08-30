"""Context Explorer projection and provenance tests."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/GraphObservatory"))
from context_projection import CANONICAL_CONTEXT_PACKS, build_context_graph  # noqa: E402
from validate_graph import validate_graph  # noqa: E402


class ContextExplorerProjectionTests(unittest.TestCase):
    def test_context_projection_is_valid_nonempty_and_deterministic(self) -> None:
        first = build_context_graph(ROOT).to_dict()
        second = build_context_graph(ROOT).to_dict()
        self.assertEqual(first, second)
        self.assertGreater(len(first["nodes"]), 0)
        self.assertEqual(validate_graph(first), [])

    def test_context_nodes_have_canonical_source_hash_and_provenance(self) -> None:
        for node in build_context_graph(ROOT).to_dict()["nodes"]:
            self.assertEqual(node["type"], "context")
            provenance = node["metadata"]["provenance"]
            self.assertIn("source_hash", provenance)
            self.assertIn("source_path", provenance)
            self.assertTrue(provenance["source_path"].startswith(CANONICAL_CONTEXT_PACKS.as_posix() + "/"))

    def test_missing_canonical_pack_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(FileNotFoundError):
                build_context_graph(Path(temp_dir))
