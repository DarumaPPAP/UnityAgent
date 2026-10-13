"""統合したSubAgentの静的契約・権限・配置を確認する。"""
import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class IntegratedSubAgentTests(unittest.TestCase):
    def test_registry_contains_exactly_four_specialists(self):
        registry = yaml.safe_load((ROOT / "subagent/registry.yaml").read_text(encoding="utf-8"))
        paths = [x["manifest"] for x in registry["entries"]]
        self.assertEqual(set(paths), {
            f"subagent/{name}/manifest.yaml"
            for name in ("artist_subagent", "graphics_subagent", "performance_subagent", "world_creator_subagent")
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
