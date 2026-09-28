"""現行Production Catalogの明示移行と観測依存を検証する。"""
import unittest
import copy
from pathlib import Path

import yaml

from Runtime.ReferenceImplementation.profiles import CATALOG
from Runtime.Contracts.reasoning_output import require_reasoning_output_contract
from Runtime.ReferenceImplementation.catalog_import_gate import CatalogImportError
from Runtime.Tests.test_catalog_import_gate import _plan


ROOT = Path(__file__).resolve().parents[2]


class ProductionSpecialistRegistrationTests(unittest.TestCase):
    def test_pinned_production_hub_snapshot_matches_current_catalog(self):
        snapshot = yaml.safe_load((ROOT / "Runtime/Tests/Fixtures/hub-production-specialists-v3.yaml").read_text(encoding="utf-8"))
        self.assertEqual(_plan(snapshot, current_catalog=CATALOG)["status"], "no_op")
        changed = copy.deepcopy(snapshot)
        graphics = next(item["manifest"] for item in changed["specialists"] if item["manifest"]["identity"]["id"] == "graphics_subagent")
        graphics["execution"]["required_observation_capabilities"] = ["project.inspect"]
        with self.assertRaises(CatalogImportError):
            _plan(changed, current_catalog=CATALOG)

    def test_graphics_and_world_are_reasoning_profiles_without_tool_backends(self):
        self.assertEqual(CATALOG.schema_version, "3.0")
        for identity, required in (("graphics_subagent", ["project.inspect", "source.read"]), ("world_creator_subagent", [])):
            with self.subTest(identity=identity):
                profile = CATALOG.get(identity)
                self.assertIsNone(profile.provider_id)
                self.assertEqual(profile.execution["kind"], "reasoning")
                self.assertEqual(profile.execution["required_observation_capabilities"], required)
                require_reasoning_output_contract(profile.execution["output_contract_ref"])
                self.assertTrue((ROOT / profile.execution["instructions_ref"]).is_file())
        self.assertEqual(CATALOG.get("artist_subagent").provider_id, "unity_artist_cli")
        self.assertNotIn("performance_subagent", CATALOG.to_mapping()["profiles"])

    def test_production_routes_use_registered_semantic_owner(self):
        routes = yaml.safe_load((ROOT / "Orchestration/Routing/task-routes.yaml").read_text(encoding="utf-8"))["routes"]
        for route in ("rendering-incident", "shader-change", "renderer-feature-change", "world-creation"):
            self.assertFalse(routes[route].get("specialist_pilot", False))
            self.assertEqual(CATALOG.get(routes[route]["specialist_profile"]).execution["kind"], "reasoning")
