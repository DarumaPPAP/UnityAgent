"""Context Pack metadata contract tests with source reference integrity."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/ContextPackValidator"))
from validate_context_packs import validate  # noqa: E402


class ContextPackMetadataContractTests(unittest.TestCase):
    def test_all_context_packs_pass_metadata_and_source_ref_validation(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_metadata_source_refs_remain_repository_relative(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("../", text, path.name)
