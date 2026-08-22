"""Context Pack metadata and semantic contract regression tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/ContextPackValidator"))
from validate_context_packs import validate  # noqa: E402

PROJECT_PROFILE_PATH = "Specs/ProjectProfile.md"
PROJECT_FALLBACK_KEY = "project_fallback"


class ContextPackMetadataContractTests(unittest.TestCase):
    def test_all_context_packs_pass_metadata_and_source_ref_validation(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_metadata_source_refs_remain_repository_relative(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("../", text, path.name)

    def test_project_profile_is_never_required_context(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            required = document.get("required", []) or []
            self.assertNotIn(PROJECT_PROFILE_PATH, required, path.name)

    def test_project_profile_is_loaded_only_from_project_fallback(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            conditional = document.get("conditional", {}) or {}
            for condition, references in conditional.items():
                if isinstance(references, list) and PROJECT_PROFILE_PATH in references:
                    self.assertEqual(condition, PROJECT_FALLBACK_KEY, path.name)
                    self.assertTrue(
                        document.get("rules", {}).get("project_profile_is_fallback_only"),
                        path.name,
                    )

    def test_routing_declares_project_fact_precedence_over_profile(self) -> None:
        index = yaml.safe_load((ROOT / ".ai/context-index.yaml").read_text(encoding="utf-8")) or {}
        rules = index.get("routing_rules", {}) or {}
        self.assertTrue(rules.get("detected_project_facts_override_project_profile"))
        self.assertTrue(rules.get("user_confirmed_project_facts_override_project_profile"))
        self.assertTrue(rules.get("project_profile_is_fallback_only"))
        self.assertTrue(rules.get("project_profile_must_not_be_required_context"))
        self.assertTrue(rules.get("project_profile_load_requires_missing_project_fact"))
