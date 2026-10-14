"""Canonical co-located subagent snapshot/canonical consumer synchronization."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "subagent/tools"))

from validate_local_subagent_catalog import validate_local_catalog
from export_snapshot import export_hub_snapshot
from unityagent.runtime.reference_implementation.catalog_import_gate import (
    HUB_MANIFEST_REF, _same_hub_contract_ref,
)


class ColocatedSubagentSourceTests(unittest.TestCase):
    def test_exact_local_snapshot_is_noop(self):
        plan = validate_local_catalog()
        self.assertEqual(plan["status"], "no_op")
        self.assertFalse(plan["apply"]["catalog_write_performed"])
        self.assertEqual(plan["source"]["ref"], "co-located://subagent/registry.yaml")

    def test_registry_contains_four_canonical_subagents(self):
        snapshot = export_hub_snapshot(ROOT)
        self.assertEqual(
            {item["manifest"]["identity"]["id"] for item in snapshot["specialists"]},
            {"artist_subagent", "graphics_subagent", "performance_subagent", "world_creator_subagent"},
        )
        for item in snapshot["specialists"]:
            self.assertIsNotNone(HUB_MANIFEST_REF.fullmatch(item["manifest_ref"]))
            self.assertTrue((ROOT / item["manifest_ref"]).is_file())

    def test_historical_contract_aliases_remain_compatible(self):
        canonical = "subagent/graphics_subagent/instructions.md"
        old = "SubAgents/graphics_subagent/instructions.md"
        legacy = "Hub/SubAgents/graphics_subagent/instructions.md"
        self.assertTrue(_same_hub_contract_ref(canonical, old))
        self.assertTrue(_same_hub_contract_ref(old, canonical))
        self.assertTrue(_same_hub_contract_ref(canonical, legacy))
        self.assertFalse(_same_hub_contract_ref(
            "subagent/performance_subagent/instructions.md", old))

if __name__ == "__main__":
    unittest.main()
