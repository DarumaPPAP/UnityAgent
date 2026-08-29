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


class ContextCutoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = load_module("phase8_context_resolver", ROOT / "Context/Selection/path_resolver.py")

    def test_prompt_templates_remain_golden_free(self):
        catalog = yaml.safe_load((ROOT / "Context/Prompt/prompt-catalog.yaml").read_text(encoding="utf-8"))
        self.assertTrue(catalog["review"]["golden_expectation_leak_reviewed"])
        self.assertFalse(catalog["review"]["golden_expected_answer_content_found"])
        for template in sorted((ROOT / "Context/Prompt/Templates").glob("*.md")):
            lowered = template.read_text(encoding="utf-8").lower()
            self.assertNotIn("expected_result:", lowered)
            self.assertNotIn("golden_task_id", lowered)

    def test_context_catalog_is_canonical_only_and_complete(self):
        catalog = yaml.safe_load((ROOT / "Context/Selection/context-catalog.yaml").read_text(encoding="utf-8"))
        self.assertTrue(catalog["materializer_requires_explicit_route_id"])
        self.assertTrue(catalog["rules"]["context_catalog_does_not_select_route"])
        routes = catalog["routes"]
        self.assertEqual(len(routes), 11)
        deprecated_scheme = "compatibility" + "://"
        for route_id, route in routes.items():
            contract = str(route["task_contract"])
            self.assertTrue(contract.startswith("Orchestration/Contracts/TaskContracts/"), route_id)
            self.assertFalse(contract.startswith(deprecated_scheme), route_id)
            self.assertTrue((ROOT / contract).is_file(), route_id)

    def test_materialized_context_uses_direct_task_contract(self):
        materializer = load_module("phase8_materializer_test", ROOT / "Context/Assembly/materialize_context.py")
        view = materializer.materialize_context("phase8-test", "csharp-local-fix", "Context/Prompt/Templates/00_full_shader_audit.md", root=ROOT)
        self.assertEqual(view["selected_refs"]["policy"][0]["resolved_path"], "Policy/User/user-policy.yaml")
        self.assertEqual(view["selected_refs"]["context_pack"]["resolved_path"], "Context/Packs/csharp-local-fix.yaml")
        self.assertEqual(view["selected_refs"]["task_contract"]["logical_ref"], "Orchestration/Contracts/TaskContracts/csharp-local-fix.yaml")
        self.assertEqual(view["selected_refs"]["task_contract"]["resolved_path"], "Orchestration/Contracts/TaskContracts/csharp-local-fix.yaml")
        self.assertIn("binding:target_source", view["unresolved_bindings"])
        self.assertNotIn("workflow_state", view)
        self.assertNotIn("checkpoint", view)
        self.assertNotIn("memory_store", view)

    def test_materialized_context_schema_and_definition_fingerprint(self):
        materializer = load_module("phase8_materializer_schema_test", ROOT / "Context/Assembly/materialize_context.py")
        view = materializer.materialize_context("phase8-schema", "architecture-design", root=ROOT)
        schema = yaml.safe_load((ROOT / "Context/Contracts/materialized-context-view.schema.yaml").read_text(encoding="utf-8"))
        fingerprint = yaml.safe_load((ROOT / "Context/Contracts/context-fingerprint.schema.yaml").read_text(encoding="utf-8"))
        definition = yaml.safe_load((ROOT / "Persistence/Contracts/definition-fingerprint.schema.yaml").read_text(encoding="utf-8"))
        resolver = RefResolver.from_schema(schema, store={
            "urn:unityagent:context:materialized-context-view": fingerprint,
            "urn:unityagent:persistence:definition-fingerprint": definition,
        })
        Draft202012Validator(schema, resolver=resolver).validate(view)
        Draft202012Validator(definition).validate(view["definition_fingerprint"])
        for value in view["definition_fingerprint"].values():
            self.assertNotIn("compatibility", str(value))

    def test_legacy_references_fail_closed(self):
        deprecated_ref = "compatibility" + "://migration-source/user-policy"
        with self.assertRaises(self.resolver.ReferenceResolutionError):
            self.resolver.resolve_for_read(deprecated_ref, ROOT)
        legacy_ref = "." + "ai/user-policy.yaml"
        with self.assertRaises(self.resolver.ReferenceResolutionError):
            self.resolver.resolve_for_read(legacy_ref, ROOT)

    def test_canonical_budget_runtime_uses_canonical_contract(self):
        canonical = load_module("phase8_budget_api_test", ROOT / "Context/Budget/budget_runtime.py")
        self.assertEqual(canonical.CONTRACT.as_posix(), "Context/Budget/context-budget.yaml")
        report = canonical.evaluate("csharp-local-fix", [100, 200], root=ROOT)
        self.assertEqual(report["decision"], "within_budget")


if __name__ == "__main__":
    unittest.main()
