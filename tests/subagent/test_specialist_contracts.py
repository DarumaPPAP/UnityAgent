import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class ProductionSpecialistsTests(unittest.TestCase):
    def test_registered_reasoning_has_no_fake_backend(self):
        registry = yaml.safe_load((ROOT / "subagent/registry.yaml").read_text(encoding="utf-8"))
        refs = {item["manifest"] for item in registry["entries"]}
        for identity in ("graphics_subagent", "world_creator_subagent", "qa_subagent"):
            reference = f"subagent/{identity}/manifest.yaml"
            self.assertIn(reference, refs)
            manifest = yaml.safe_load((ROOT / reference).read_text(encoding="utf-8"))
            self.assertEqual(manifest["execution"]["kind"], "reasoning")
            self.assertEqual(manifest["backends"], [])
            self.assertFalse(manifest["installation"]["auto_install"])
            self.assertFalse(manifest["installation"]["required"])
            self.assertNotIn("model", manifest["execution"])
            for name in ("instructions_ref", "output_contract_ref"):
                self.assertTrue((ROOT / manifest["execution"][name]).is_file())
        performance = yaml.safe_load((ROOT / "subagent/qa_subagent/manifest.yaml").read_text(encoding="utf-8"))
        self.assertEqual(performance["execution"]["required_observation_capabilities"], ["profiler.observe"])


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


class PerformanceCandidateContractTests(unittest.TestCase):
    def test_candidate_baseline_is_read_only_and_production_contract_keeps_the_boundary(self) -> None:
        contract = yaml.safe_load((ROOT / "subagent/qa_subagent/contracts/capability-contracts.yaml").read_text(encoding="utf-8"))
        registry = yaml.safe_load((ROOT / "subagent/registry.yaml").read_text(encoding="utf-8"))
        self.assertEqual(contract["status"], "pilot_unregistered")
        self.assertEqual(contract["identity"], "qa_subagent")
        self.assertEqual(set(contract["capabilities"]), {"performance.analyze"})
        self.assertEqual(contract["capabilities"]["performance.analyze"]["mode"], "read_only")
        self.assertEqual(contract["evidence"]["required_type"], "performance_analysis")
        self.assertEqual(contract["evidence"]["unobserved_runtime"], "NOT_EVALUATED_RUNTIME")
        self.assertEqual(contract["boundaries"]["provider_resolution"], "unity_agent_tool_broker_only")
        self.assertEqual(contract["boundaries"]["mutation"], "prohibited_during_pilot")
        self.assertIn("subagent/qa_subagent/manifest.yaml", {entry["manifest"] for entry in registry["entries"]})
        production = yaml.safe_load((ROOT / "subagent/qa_subagent/contracts/production-capability-contract.yaml").read_text(encoding="utf-8"))
        self.assertEqual(production["observations"]["required"], ["profiler.observe"])
        self.assertEqual(production["boundaries"]["provider_selection"], "prohibited")


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

class IntegratedSubAgentTests(unittest.TestCase):
    def test_registry_contains_exactly_four_specialists(self):
        registry = yaml.safe_load((ROOT / "subagent/registry.yaml").read_text(encoding="utf-8"))
        paths = [x["manifest"] for x in registry["entries"]]
        self.assertEqual(set(paths), {
            f"subagent/{name}/manifest.yaml"
            for name in ("artist_subagent", "graphics_subagent", "qa_subagent", "world_creator_subagent")
        })
        self.assertEqual(len(paths), len(set(paths)))

    def test_no_unreviewed_authorization_expansion(self):
        registry = yaml.safe_load((ROOT / "subagent/registry.yaml").read_text(encoding="utf-8"))
        for row in registry["entries"]:
            manifest = yaml.safe_load((ROOT / row["manifest"]).read_text(encoding="utf-8"))
            self.assertFalse(manifest["installation"]["auto_install"])
            self.assertFalse(manifest["installation"]["required"])
            identity = manifest["identity"]["id"]
            if identity == "artist_subagent":
                self.assertEqual("provider_backed", manifest["execution"]["kind"])
            else:
                self.assertEqual("reasoning", manifest["execution"]["kind"])
                self.assertEqual([], manifest["backends"])
                self.assertIn(manifest["execution"]["execution_mode"], {"read_only_analysis", "planning_only"})
                self.assertTrue((ROOT / manifest["execution"]["instructions_ref"]).is_file())

    def test_layout_root_uses_subagent_not_specialists(self):
        config = json.loads((ROOT / "repository-layout.json").read_text(encoding="utf-8"))
        self.assertIn("subagent", config["allowed_roots"])
        self.assertNotIn("specialists", config["allowed_roots"])

if __name__ == "__main__":
    unittest.main()
