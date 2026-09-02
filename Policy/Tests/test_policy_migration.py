from pathlib import Path
import importlib.util
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PolicyCutoverTests(unittest.TestCase):
    def test_canonical_user_policy_integrity(self):
        validator = load_module("policy_integrity", ROOT / "Policy/Validators/validate_user_policy_integrity.py")
        self.assertEqual(validator.validate(ROOT), [])

    def test_capability_and_mcp_runtime_authorities_remain_split(self):
        capability_context = yaml.safe_load(
            (ROOT / "Context/Selection/tool-capability-catalog.yaml").read_text(encoding="utf-8")
        )
        runtime = yaml.safe_load((ROOT / "Runtime/Permissions/mcp-activation.yaml").read_text(encoding="utf-8"))
        trust = yaml.safe_load((ROOT / "Policy/Security/tool-trust.yaml").read_text(encoding="utf-8"))
        permissions = yaml.safe_load((ROOT / "Policy/Security/permissions.yaml").read_text(encoding="utf-8"))
        ownership = yaml.safe_load((ROOT / "Policy/Contracts/repository-ownership.yaml").read_text(encoding="utf-8"))
        self.assertEqual(capability_context["authority"], "Context")
        self.assertTrue(capability_context["rules"]["context_does_not_select_provider"])
        self.assertFalse((ROOT / "Context/Selection/mcp-selection.yaml").exists())
        for level in ("level_2", "level_3", "level_4", "level_5"):
            self.assertIn(level, runtime["tool_exposure"])
        self.assertIn("source_read_policy", trust)
        self.assertEqual(
            permissions["requirements"]["mutate"]["requires"],
            ["approved_plan", "explicit_mutation_permission", "revision", "diff", "undo_path"],
        )
        self.assertEqual(
            permissions["requirements"]["bake"]["requires"],
            ["separate_explicit_bake_permission", "dependency_invalidation"],
        )
        self.assertEqual(ownership["repositories"]["policy"], "DarumaPPAP/UnityAgent")
        self.assertEqual(ownership["repositories"]["mcp"], "DarumaPPAP/MyUnityMCP")


if __name__ == "__main__":
    unittest.main()
