"""Route, Context Pack, Task Contract, Skill, and Knowledge binding tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class RouteContextBindingTests(unittest.TestCase):
    def test_every_route_resolves_one_pack_contract_and_skill(self) -> None:
        index = yaml.safe_load((ROOT / ".ai/context-index.yaml").read_text(encoding="utf-8"))
        for route in (index.get("routes", {}) or {}).values():
            self.assertTrue((ROOT / route["context_pack"]).is_file())
            self.assertTrue((ROOT / route["task_contract"]).is_file())
            self.assertTrue((ROOT / ".agents/skills" / route["primary_skill"] / "SKILL.md").is_file())

    def test_context_expansion_is_one_hop_for_every_pack(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(document["limits"]["context_expansion_hops"], 1, path.name)

    def test_metadata_is_not_used_as_execution_rule(self) -> None:
        for path in (ROOT / ".ai/context-packs").glob("*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertIn("rules", document)
            self.assertIn("metadata", document)
            self.assertIsNot(document["rules"], document["metadata"])
