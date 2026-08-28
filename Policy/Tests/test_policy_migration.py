from pathlib import Path
import importlib.util
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]

def load_resolver():
    path = ROOT / "Context/Compatibility/path_resolver.py"
    spec = importlib.util.spec_from_file_location("phase2_policy_test_resolver", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class PolicyMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = load_resolver()

    def test_user_policy_and_risk_are_byte_exact(self):
        pairs = (
            ("compatibility://migration-source/user-policy", "Policy/User/user-policy.yaml"),
            ("compatibility://migration-source/risk-levels", "Policy/Risk/risk-levels.yaml"),
        )
        for source_ref, canonical in pairs:
            source = self.resolver.resolve_for_read(source_ref, ROOT)
            self.assertEqual(source.read_bytes(), (ROOT / canonical).read_bytes(), source_ref)

    def test_mcp_activation_is_split_without_fact_loss(self):
        legacy_path = self.resolver.resolve_for_read("compatibility://migration-source/mcp-activation", ROOT)
        legacy = yaml.safe_load(legacy_path.read_text(encoding="utf-8"))
        selection = yaml.safe_load((ROOT / "Context/Selection/mcp-selection.yaml").read_text(encoding="utf-8"))
        runtime = yaml.safe_load((ROOT / "Runtime/Permissions/mcp-activation.yaml").read_text(encoding="utf-8"))
        trust = yaml.safe_load((ROOT / "Policy/Security/tool-trust.yaml").read_text(encoding="utf-8"))
        permissions = yaml.safe_load((ROOT / "Policy/Security/permissions.yaml").read_text(encoding="utf-8"))
        ownership = yaml.safe_load((ROOT / "Policy/Contracts/repository-ownership.yaml").read_text(encoding="utf-8"))

        self.assertEqual(legacy["catalogs"], selection["catalogs"])
        self.assertEqual(legacy["selection"], selection["selection"])
        self.assertEqual(legacy["activation"]["level_0"], selection["context_activation"]["level_0"])
        self.assertEqual(legacy["activation"]["level_1"], selection["context_activation"]["level_1"])
        for level in ("level_2", "level_3", "level_4", "level_5"):
            self.assertEqual(legacy["activation"][level], runtime["tool_exposure"][level])
        self.assertEqual(legacy["standard_tool_group_order"], runtime["standard_tool_group_order"])
        self.assertEqual(legacy["source_read_policy"], trust["source_read_policy"])
        for key in ("inspect_is_read_only", "plan_is_read_only", "automatic_save", "silent_fallback", "visual_acceptance_requires_human_review"):
            self.assertEqual(legacy["safety"][key], trust["safety"][key])
        self.assertTrue(legacy["safety"]["mutate_requires_revision_diff_undo_and_explicit_permission"])
        self.assertTrue(legacy["safety"]["bake_requires_dependency_invalidation_and_separate_permission"])
        self.assertEqual(
            permissions["requirements"]["mutate"]["requires"],
            ["approved_plan", "explicit_mutation_permission", "revision", "diff", "undo_path"],
        )
        self.assertEqual(
            permissions["requirements"]["bake"]["requires"],
            ["separate_explicit_bake_permission", "dependency_invalidation"],
        )
        self.assertEqual(legacy["repositories"], ownership["repositories"])
        self.assertEqual(legacy["ownership"], ownership["ownership"])

if __name__ == "__main__":
    unittest.main()
