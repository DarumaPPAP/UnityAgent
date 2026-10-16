from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


class GraphicsCandidateContractTests(unittest.TestCase):
    def test_candidate_baseline_stays_read_only_and_is_not_the_production_contract(self) -> None:
        contract = yaml.safe_load((ROOT / "subagent/graphics_subagent/contracts/capability-contracts.yaml").read_text(encoding="utf-8"))
        registry = yaml.safe_load((ROOT / "subagent/registry.yaml").read_text(encoding="utf-8"))
        self.assertEqual(contract["status"], "pilot_unregistered")
        self.assertEqual(set(contract["capabilities"]), {"graphics.inspect", "graphics.diagnose", "graphics.validate"})
        self.assertTrue(all(capability["mode"] == "read_only" for capability in contract["capabilities"].values()))
        self.assertEqual(contract["boundaries"]["mutation"], "prohibited_during_pilot")
        self.assertEqual(contract["evidence"]["unobserved_runtime"], "NOT_EVALUATED_RUNTIME")
        manifest_ref = next(entry["manifest"] for entry in registry["entries"] if "graphics_subagent" in entry["manifest"])
        manifest = yaml.safe_load((ROOT / manifest_ref).read_text(encoding="utf-8"))
        self.assertNotEqual(manifest["capability_contract_ref"], "subagent/graphics_subagent/contracts/capability-contracts.yaml")
        self.assertEqual(manifest["execution"]["kind"], "reasoning")


if __name__ == "__main__":
    unittest.main()
