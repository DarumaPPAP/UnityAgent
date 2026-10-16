from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


class WorldCreatorCandidateContractTests(unittest.TestCase):
    def test_providerless_candidate_baseline_is_not_the_production_contract(self) -> None:
        contract = yaml.safe_load((ROOT / "subagent/world_creator_subagent/contracts/capability-contracts.yaml").read_text(encoding="utf-8"))
        registry = yaml.safe_load((ROOT / "subagent/registry.yaml").read_text(encoding="utf-8"))
        self.assertEqual(contract["status"], "pilot_unregistered")
        self.assertEqual(contract["identity"], "world_creator_subagent")
        self.assertEqual(set(contract["capabilities"]), {"world.plan"})
        self.assertEqual(contract["capabilities"]["world.plan"]["mode"], "planning_only")
        self.assertEqual(contract["boundaries"]["provider_resolution"], "not_required")
        self.assertEqual(contract["boundaries"]["mutation"], "prohibited_during_pilot")
        self.assertEqual(contract["evidence"]["receipt"], "not_required_source_context_binding")
        self.assertNotIn("backends", contract)
        self.assertEqual(contract["evidence"]["unobserved_runtime"], "NOT_EVALUATED_RUNTIME")
        manifest_ref = next(entry["manifest"] for entry in registry["entries"] if "world_creator_subagent" in entry["manifest"])
        manifest = yaml.safe_load((ROOT / manifest_ref).read_text(encoding="utf-8"))
        self.assertNotEqual(manifest["capability_contract_ref"], "subagent/world_creator_subagent/contracts/capability-contracts.yaml")
        self.assertEqual(manifest["backends"], [])


if __name__ == "__main__":
    unittest.main()
