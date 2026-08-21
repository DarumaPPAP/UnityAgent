"""Deterministic Full and Incremental Context Catalog tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/ContextCatalog"))
from build_context_catalog import build_index, serialize  # noqa: E402


class ContextCatalogReproducibilityTests(unittest.TestCase):
    def test_full_and_changed_builds_have_identical_bytes(self) -> None:
        self.assertEqual(serialize(build_index(ROOT)), serialize(build_index(ROOT, changed_only=True)))

    def test_index_contains_only_exploration_fields(self) -> None:
        index = build_index(ROOT)
        forbidden = {"purpose", "decisions", "forbidden", "rules", "transcript", "evidence"}
        for context in index["contexts"]:
            self.assertTrue(forbidden.isdisjoint(context))
            self.assertIn("source_sha256", context)
