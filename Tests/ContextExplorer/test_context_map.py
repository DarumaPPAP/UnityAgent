"""Context Explorer derived-map and provenance tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/ContextExplorer"))
from architecture_projection import build_human_architecture  # noqa: E402
from build import write_bundle  # noqa: E402
from context_map import CANONICAL_CONTEXT_PACKS, load_context_map, validate_context_map  # noqa: E402


class ContextExplorerMapTests(unittest.TestCase):
    def test_context_map_is_valid_nonempty_and_deterministic(self) -> None:
        first = load_context_map(ROOT).to_dict()
        second = load_context_map(ROOT).to_dict()
        self.assertEqual(first, second)
        self.assertGreater(len(first["nodes"]), 0)
        self.assertEqual(first["metadata"]["kind"], "unityagent-context-map")
        self.assertTrue(first["metadata"]["read_only"])
        self.assertEqual(validate_context_map(first), [])

    def test_context_nodes_have_canonical_source_hash_and_provenance(self) -> None:
        for node in load_context_map(ROOT).to_dict()["nodes"]:
            self.assertEqual(node["type"], "context")
            provenance = node["metadata"]["provenance"]
            self.assertRegex(provenance["source_hash"], r"^[0-9a-f]{64}$")
            self.assertTrue(provenance["source_path"].startswith(CANONICAL_CONTEXT_PACKS.as_posix() + "/"))

    def test_generated_relations_only_target_existing_contexts(self) -> None:
        document = load_context_map(ROOT).to_dict()
        ids = {node["id"] for node in document["nodes"]}
        for edge in document["edges"]:
            self.assertIn(edge["source"], ids)
            self.assertIn(edge["target"], ids)
            self.assertTrue(edge["relation"])
            self.assertEqual(edge["metadata"]["provenance"], "explicit_context_metadata_relation")

    def test_missing_canonical_pack_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(FileNotFoundError):
                load_context_map(Path(temp_dir))

    def test_human_architecture_is_deterministic_and_uses_seven_concepts(self) -> None:
        first = build_human_architecture(ROOT)
        second = build_human_architecture(ROOT)
        self.assertEqual(first, second)
        self.assertEqual(
            [concept["id"] for concept in first["concepts"]],
            ["rules", "planner", "knowledge", "executor", "evidence", "memory", "quality"],
        )
        for concept in first["concepts"]:
            for relative in concept["source_paths"]:
                self.assertTrue((ROOT / relative).exists(), f"missing drill-down source: {relative}")

    def test_context_map_schema_has_canonical_shape(self) -> None:
        schema = json.loads(
            (ROOT / "Tools/ContextExplorer/schema/context-map.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(schema["required"]), {"metadata", "nodes", "edges"})
        metadata = schema["properties"]["metadata"]["properties"]
        self.assertEqual(metadata["kind"]["const"], "unityagent-context-map")
        self.assertTrue(metadata["read_only"]["const"])

    def test_static_bundle_embeds_context_map_not_legacy_graph_marker(self) -> None:
        context_map = load_context_map(ROOT)
        architecture = build_human_architecture(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "viewer"
            write_bundle(ROOT, context_map, architecture, output)
            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("window.__CONTEXT_MAP__ = {", html)
            self.assertNotIn("window.__CONTEXT_MAP__ = null;", html)
            self.assertNotIn("__CONTEXT_GRAPH__", html)
            self.assertTrue((output / "context-map.json").is_file())


if __name__ == "__main__":
    unittest.main()
