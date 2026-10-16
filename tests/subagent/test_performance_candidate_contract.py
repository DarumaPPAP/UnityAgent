from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


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


if __name__ == "__main__":
    unittest.main()
