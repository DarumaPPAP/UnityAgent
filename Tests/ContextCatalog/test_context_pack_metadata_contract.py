"""Context Pack v3 metadata, typing, and semantic contract regression tests."""

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
CONTEXT_TYPES = {
    "binding",
    "repository_reference",
    "external_reference",
    "context_include",
    "route_handoff",
}


def is_project_profile_reference(item: object) -> bool:
    return (
        isinstance(item, dict)
        and item.get("type") == "repository_reference"
        and item.get("path") == PROJECT_PROFILE_PATH
    )


class ContextPackMetadataContractTests(unittest.TestCase):
    def test_all_context_packs_pass_metadata_and_source_ref_validation(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_metadata_source_refs_remain_repository_relative(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("../", text, path.name)

    def test_required_and_conditional_context_entries_are_typed(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            self.assertEqual(str(document.get("schema_version")), "3.0", path.name)

            for item in document.get("required", []) or []:
                self.assertIsInstance(item, dict, path.name)
                self.assertIn(item.get("type"), CONTEXT_TYPES, path.name)

            for condition, references in (document.get("conditional", {}) or {}).items():
                self.assertIsInstance(references, list, f"{path.name}:{condition}")
                for item in references:
                    self.assertIsInstance(item, dict, f"{path.name}:{condition}")
                    self.assertIn(item.get("type"), CONTEXT_TYPES, f"{path.name}:{condition}")

    def test_project_profile_is_never_required_context(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            required = document.get("required", []) or []
            self.assertFalse(
                any(is_project_profile_reference(item) for item in required),
                path.name,
            )

    def test_project_profile_is_loaded_only_from_project_fallback(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            conditional = document.get("conditional", {}) or {}
            for condition, references in conditional.items():
                for item in references or []:
                    if is_project_profile_reference(item):
                        self.assertEqual(condition, PROJECT_FALLBACK_KEY, path.name)
                        self.assertTrue(
                            document.get("rules", {}).get("project_profile_is_fallback_only"),
                            path.name,
                        )

    def test_external_references_are_not_repository_references(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            sections = [document.get("required", []) or []]
            sections.extend((document.get("conditional", {}) or {}).values())
            for items in sections:
                for item in items or []:
                    if not isinstance(item, dict) or item.get("type") != "external_reference":
                        continue
                    self.assertIn("repository", item, path.name)
                    self.assertIn("path", item, path.name)
                    self.assertNotIn("source_path", item, path.name)

    def test_context_include_and_route_handoff_are_distinct(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            sections = [document.get("required", []) or []]
            sections.extend((document.get("conditional", {}) or {}).values())
            for items in sections:
                for item in items or []:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "context_include":
                        self.assertIn("context_id", item, path.name)
                        self.assertNotIn("route_id", item, path.name)
                    elif item.get("type") == "route_handoff":
                        self.assertIn("route_id", item, path.name)
                        self.assertNotIn("context_id", item, path.name)

    def test_routing_declares_project_fact_precedence_over_profile(self) -> None:
        index = yaml.safe_load((ROOT / ".ai/context-index.yaml").read_text(encoding="utf-8")) or {}
        rules = index.get("routing_rules", {}) or {}
        self.assertTrue(rules.get("detected_project_facts_override_project_profile"))
        self.assertTrue(rules.get("user_confirmed_project_facts_override_project_profile"))
        self.assertTrue(rules.get("project_profile_is_fallback_only"))
        self.assertTrue(rules.get("project_profile_must_not_be_required_context"))
        self.assertTrue(rules.get("project_profile_load_requires_missing_project_fact"))


if __name__ == "__main__":
    unittest.main()
