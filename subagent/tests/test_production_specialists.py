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
