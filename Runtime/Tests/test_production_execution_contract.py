import copy
import unittest
from pathlib import Path

import yaml

from Runtime.ReferenceImplementation.profiles import CATALOG, ProfileValidationError, SubAgentProfileCatalog
from Runtime.ReferenceImplementation.catalog_import_gate import CatalogImportError
from Runtime.Tests.test_catalog_import_gate import _hub_v2_snapshot, _plan


class ProductionExecutionContractTests(unittest.TestCase):
    def catalog(self):
        value = yaml.safe_load((Path(__file__).resolve().parents[2] / "Runtime/Tests/Fixtures/artist-consumer-v1.yaml").read_text(encoding="utf-8"))
        value["schema_version"] = "3.0"
        for profile in value["profiles"].values():
            profile["execution"] = {"kind": "provider_backed"}
        reasoning = {"profile_id": "planner_subagent", "display_name": "Planner", "audience": "planner_subagent", "goal_type": "plan.create", "capabilities": ["plan.create"], "primary_capability": "plan.create", "required_evidence": ["plan"], "activation": {"install_mode": "optional", "auto_install": False, "required_environment": ["project.exists"]}, "evidence": {"source_type": "reasoning", "producer": "Runtime", "provenance_token": "planner_subagent"}, "execution": {"kind": "reasoning", "reasoning_runtime": "codex_runner", "execution_mode": "planning_only", "instructions_ref": ".agents/skills/world-planning/SKILL.md", "output_contract_ref": "Runtime/Contracts/world-plan-result.schema.json", "source_context_binding": "required", "required_observation_capabilities": []}}
        value["profiles"]["planner_subagent"] = reasoning
        reasoning["execution"]["hub_contract_refs"] = {"instructions_ref": "SubAgents/planner_subagent/instructions.md", "output_contract_ref": "SubAgents/planner_subagent/contracts/result.schema.json"}
        reasoning["selection"] = {"compatibility": {"unity_version_prefixes": ["6000."], "context_values": {}}, "capability_context": {"plan.create": {"all_of": ["task_fact:world_goal"], "any_of": [], "receipt_required": False}}}
        reasoning["selection"]["supported_targets"] = _hub_v2_snapshot()["specialists"][0]["manifest"]["compatibility"]["supported_targets"]
        return value

    def test_v3_preserves_artist_and_supports_reasoning_without_provider_identity(self):
        value = self.catalog()
        parsed = SubAgentProfileCatalog.from_mapping(value)
        self.assertEqual(parsed.to_mapping(), value)
        self.assertEqual(parsed.get("artist_subagent").provider_id, "unity_artist_cli")
        self.assertIsNone(parsed.get("planner_subagent").provider_id)
        self.assertEqual(parsed.get("artist_subagent").default_scope, CATALOG.get("artist_subagent").default_scope)

    def test_reasoning_provider_null_is_also_prohibited(self):
        for provider in (None, "fake_provider"):
            value = self.catalog()
            value["profiles"]["planner_subagent"]["provider_id"] = provider
            with self.assertRaises(ProfileValidationError):
                SubAgentProfileCatalog.from_mapping(value)

    def test_provider_backed_requires_provider_and_v2_does_not_accept_v3(self):
        value = self.catalog()
        value["profiles"]["artist_subagent"].pop("provider_id")
        with self.assertRaises(ProfileValidationError):
            SubAgentProfileCatalog.from_mapping(value)
        value = self.catalog()
        value["schema_version"] = "2.0"
        with self.assertRaises(ProfileValidationError):
            SubAgentProfileCatalog.from_mapping(value)

    def test_reasoning_rejects_mutation_and_semantic_observation_dispatch(self):
        for mutation in ("scope", "observations"):
            value = self.catalog()
            profile = value["profiles"]["planner_subagent"]
            if mutation == "scope":
                profile["scope"] = {}
            else:
                profile["execution"]["required_observation_capabilities"] = ["plan.create"]
            with self.assertRaises(ProfileValidationError):
                SubAgentProfileCatalog.from_mapping(value)

    def test_hub_v5_import_preserves_reasoning_and_detects_contract_drift(self):
        consumer = SubAgentProfileCatalog.from_mapping(self.catalog())
        snapshot = _hub_v2_snapshot()
        snapshot["schema_version"] = "3.0"
        artist = snapshot["specialists"][0]["manifest"]
        artist["schema_version"] = "5.0"
        artist["execution"] = {"kind": "provider_backed"}
        planner = copy.deepcopy(artist)
        planner.update(identity={"id": "planner_subagent", "name": "Planner", "version": "1.0"}, capabilities=[{"id": "plan", "operations": ["create"]}], backends=[], dependencies=[])
        planner["activation"]["required_before_resolution"] = ["project.exists"]
        planner["evidence"]["runtime_types"] = ["plan"]
        execution = consumer.get("planner_subagent").execution
        planner["execution"] = {key: execution[key] for key in ("kind", "reasoning_runtime", "execution_mode", "source_context_binding", "required_observation_capabilities")}
        planner["execution"].update(execution["hub_contract_refs"])
        snapshot["specialists"].append({"manifest_ref": "SubAgents/planner_subagent/manifest.yaml", "manifest": planner})
        self.assertEqual(_plan(snapshot, current_catalog=consumer)["status"], "no_op")
        planner["execution"]["output_contract_ref"] = "SubAgents/planner_subagent/contracts/changed.schema.json"
        with self.assertRaises(CatalogImportError) as caught:
            _plan(snapshot, current_catalog=consumer)
        self.assertEqual(caught.exception.code, "execution_contract_mismatch")

    def test_admission_is_supported_by_actual_provider_registry(self):
        root = Path(__file__).resolve().parents[2]
        admission = yaml.safe_load((root / "Runtime/Tests/Fixtures/specialist-execution-admission.yaml").read_text(encoding="utf-8"))
        registry = yaml.safe_load((root / "Runtime/Tooling/provider_registry.yaml").read_text(encoding="utf-8"))
        capabilities = {capability for provider in registry["providers"].values() if provider.get("production_enabled", True) for capability in provider["capabilities"]}
        for row in admission["specialists"]:
            self.assertFalse(set(row["semantic_capabilities"]) & capabilities)
            self.assertEqual(set(row["required_observation_capabilities"]) - capabilities, set(row["production_observation_gaps"]))


if __name__ == "__main__":
    unittest.main()
