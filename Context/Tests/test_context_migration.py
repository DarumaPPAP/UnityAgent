from pathlib import Path
import importlib.util
import unittest
import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class ContextMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = load_module("phase2_context_test_resolver", ROOT / "Context/Compatibility/path_resolver.py")

    def test_prompt_templates_are_lossless_and_golden_free(self):
        catalog = yaml.safe_load((ROOT / "Context/Prompt/prompt-catalog.yaml").read_text(encoding="utf-8"))
        self.assertTrue(catalog["review"]["golden_expectation_leak_reviewed"])
        self.assertFalse(catalog["review"]["golden_expected_answer_content_found"])
        for old in sorted((ROOT / "Prompt").glob("*.md")):
            new = ROOT / "Context/Prompt/Templates" / old.name
            self.assertTrue(new.is_file(), old.name)
            self.assertEqual(old.read_bytes(), new.read_bytes(), old.name)
            lowered = new.read_text(encoding="utf-8").lower()
            self.assertNotIn("expected_result:", lowered)
            self.assertNotIn("golden_task_id", lowered)

    def test_context_packs_are_lossless(self):
        old_dir = self.resolver.resolve_for_read("compatibility://migration-source/context-packs", ROOT)
        new_dir = ROOT / "Context/Packs"
        old_files = sorted(p.name for p in old_dir.glob("*.yaml"))
        new_files = sorted(p.name for p in new_dir.glob("*.yaml"))
        self.assertEqual(old_files, new_files)
        for name in old_files:
            self.assertEqual((old_dir / name).read_bytes(), (new_dir / name).read_bytes(), name)

    def test_knowledge_is_lossless(self):
        old_dir = self.resolver.resolve_for_read("compatibility://migration-source/knowledge", ROOT)
        new_dir = ROOT / "Context/Retrieval/Knowledge"
        old_files = sorted(p.relative_to(old_dir).as_posix() for p in old_dir.rglob("*") if p.is_file())
        for rel in old_files:
            self.assertTrue((new_dir / rel).is_file(), rel)
            self.assertEqual((old_dir / rel).read_bytes(), (new_dir / rel).read_bytes(), rel)
        pilot = self.resolver.resolve_for_read("compatibility://migration-source/knowledge-graph-pilot", ROOT)
        self.assertEqual(pilot.read_bytes(), (new_dir / "knowledge-graph-pilot.yaml").read_bytes())

    def test_context_catalog_preserves_materialization_mapping_without_route_authority(self):
        legacy_path = self.resolver.resolve_for_read("compatibility://migration-source/routing-index", ROOT)
        legacy = yaml.safe_load(legacy_path.read_text(encoding="utf-8"))
        catalog = yaml.safe_load((ROOT / "Context/Selection/context-catalog.yaml").read_text(encoding="utf-8"))
        self.assertTrue(catalog["materializer_requires_explicit_route_id"])
        self.assertTrue(catalog["rules"]["context_catalog_does_not_select_route"])
        legacy_ids = {str(value["id"]) for value in legacy["routes"].values()}
        self.assertEqual(legacy_ids, set(catalog["routes"]))
        by_id = {str(value["id"]): value for value in legacy["routes"].values()}
        for route_id, current in catalog["routes"].items():
            old = by_id[route_id]
            old_pack = self.resolver.resolve_reference(str(old["context_pack"]), ROOT)
            self.assertEqual(old_pack, str(current["context_pack"]))
            self.assertEqual(str(old["primary_skill"]), Path(str(current["primary_skill"])).parent.name)

    def test_materialized_context_is_current_call_view(self):
        materializer = load_module("phase2_materializer_test", ROOT / "Context/Assembly/materialize_context.py")
        view = materializer.materialize_context("phase2-test", "csharp-local-fix", "Context/Prompt/Templates/00_full_shader_audit.md", root=ROOT)
        self.assertEqual(view["selected_refs"]["policy"][0]["resolved_path"], "Policy/User/user-policy.yaml")
        self.assertEqual(view["selected_refs"]["context_pack"]["resolved_path"], "Context/Packs/csharp-local-fix.yaml")
        self.assertTrue(view["selected_refs"]["task_contract"]["logical_ref"].startswith("compatibility://"))
        self.assertTrue(view["selected_refs"]["task_contract"]["resolved_path"].endswith("harness/task-contracts/csharp-local-fix.yaml"))
        self.assertIn("binding:target_source", view["unresolved_bindings"])
        self.assertEqual(view["budget_report"]["decision"], "unmeasured")
        self.assertNotIn("workflow_state", view)
        self.assertNotIn("checkpoint", view)
        self.assertNotIn("memory_store", view)
        required_paths = {item["resolved_path"] for item in view["selected_refs"]["required_context"]}
        self.assertIn("SkillReferences/CODING_STANDARDS.md", required_paths)
        self.assertIn("SkillReferences/CODE_FORMATTING_STANDARDS.md", required_paths)

    def test_materialized_context_schema_uses_phase1_definition_fingerprint(self):
        materializer = load_module("phase2_materializer_schema_test", ROOT / "Context/Assembly/materialize_context.py")
        view = materializer.materialize_context("phase2-schema", "architecture-design", root=ROOT)
        schema = yaml.safe_load((ROOT / "Context/Contracts/materialized-context-view.schema.yaml").read_text(encoding="utf-8"))
        fingerprint = yaml.safe_load((ROOT / "Context/Contracts/context-fingerprint.schema.yaml").read_text(encoding="utf-8"))
        definition = yaml.safe_load((ROOT / "Persistence/Contracts/definition-fingerprint.schema.yaml").read_text(encoding="utf-8"))
        resolver = RefResolver.from_schema(schema, store={"context-fingerprint.schema.yaml": fingerprint, "../../Persistence/Contracts/definition-fingerprint.schema.yaml": definition})
        Draft202012Validator(schema, resolver=resolver).validate(view)
        Draft202012Validator(definition).validate(view["definition_fingerprint"])

    def test_compatibility_is_read_only_and_fails_closed(self):
        with self.assertRaises(self.resolver.CompatibilityError):
            self.resolver.resolve_for_write("compatibility://migration-source/user-policy", ROOT)
        with self.assertRaises(self.resolver.CompatibilityError):
            self.resolver.resolve_for_read("compatibility://does-not-exist", ROOT)

    def test_budget_engine_is_lossless_with_canonical_contract_override(self):
        canonical = load_module("phase2_budget_api_test", ROOT / "Context/Budget/context_budget_runtime.py")
        source = ROOT / "Tools/ContextBudget/context_budget_runtime.py"
        migrated = ROOT / "Context/Budget/_compat_engine.py"
        validation_source = ROOT / "Tools/ContextBudget/context_budget_validation.py"
        validation_migrated = ROOT / "Context/Budget/_compat_validation.py"
        self.assertEqual(source.read_bytes(), migrated.read_bytes())
        self.assertEqual(validation_source.read_bytes(), validation_migrated.read_bytes())
        self.assertEqual(canonical.BUDGET_CONTRACT_PATH.as_posix(), "Context/Budget/context-budget.yaml")
        self.assertEqual(canonical.estimate_tokens(10, 3), 4)

if __name__ == "__main__":
    unittest.main()
