"""Effective Harness Runtime ownership and invariant tests."""
from __future__ import annotations

import unittest
from pathlib import Path

from Runtime.Harnesses.effective_harness import build_effective_harness, validate_effective_harness

ROOT = Path(__file__).resolve().parents[2]
TASK_CONTRACT_ROOT = ROOT / "Orchestration/Contracts/TaskContracts"


def contract(name: str) -> str:
    return f"Orchestration/Contracts/TaskContracts/{name}.yaml"


def build(name: str, *, profile: str | None = None, request: dict | None = None) -> dict:
    path = contract(name)
    if profile is None:
        import yaml

        data = yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}
        profile = data["default_execution_profile"]
    return build_effective_harness(
        ROOT,
        path,
        route_id=name,
        execution_profile=profile,
        request=request or {},
    )


class EffectiveHarnessRuntimeTests(unittest.TestCase):
    def test_all_task_contracts_resolve_without_invariant_errors(self) -> None:
        import yaml

        for path in sorted(TASK_CONTRACT_ROOT.glob("*.yaml")):
            if path.name == "task-contract.schema.yaml":
                continue
            relative = path.relative_to(ROOT).as_posix()
            contract_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            document = build_effective_harness(
                ROOT,
                relative,
                route_id=path.stem,
                execution_profile=contract_data["default_execution_profile"],
            )
            self.assertEqual(validate_effective_harness(document), [], path.name)

    def test_selection_inputs_are_explicit_and_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_effective_harness(
                ROOT,
                contract("csharp-local-fix"),
                route_id="",
                execution_profile="personal_full_control",
            )
        with self.assertRaises(ValueError):
            build_effective_harness(
                ROOT,
                contract("csharp-local-fix"),
                route_id="csharp-local-fix",
                execution_profile="",
            )

    def test_runtime_does_not_reverse_lookup_context_routes(self) -> None:
        source = (ROOT / "Runtime/Harnesses/effective_harness.py").read_text(encoding="utf-8")
        self.assertNotIn("Context/Selection", source)
        self.assertNotIn("context-catalog", source)
        self.assertNotIn("route_for_contract", source)
        self.assertNotIn("Orchestration.Routing", source)

    def test_contract_id_does_not_infer_human_gate_semantics(self) -> None:
        source = (ROOT / "Runtime/Harnesses/effective_harness.py").read_text(encoding="utf-8")
        self.assertNotIn('"visual" in contract', source)
        document = build("visual-direction")
        self.assertFalse(any(gate.get("id") == "visual_review" for gate in document["human_gates"]))
        self.assertIn("graphics_compare", [gate["id"] for gate in document["quality_gates"]["required"]])

    def test_r0_always_blocks_mutation(self) -> None:
        document = {
            "route_id": "r",
            "execution_profile": "generic_planning",
            "risk_level": "R0",
            "permission": {"mutate": "allowed"},
            "allowed_mutations": [],
        }
        self.assertIn("R0 must block mutation", validate_effective_harness(document))

    def test_prohibited_mutation_wins_over_allowed_mutation(self) -> None:
        document = {
            "route_id": "r",
            "execution_profile": "personal_full_control",
            "risk_level": "R1",
            "permission": {"mutate": "allowed"},
            "allowed_mutations": ["x"],
            "prohibited_mutations": ["x"],
            "mutation_channels": ["csharp"],
        }
        self.assertIn("Mutation cannot be both allowed and prohibited", validate_effective_harness(document))

    def test_unresolved_binding_clears_direct_mutation(self) -> None:
        document = {
            "route_id": "r",
            "execution_profile": "personal_full_control",
            "risk_level": "R1",
            "permission": {"mutate": "approval-dependent"},
            "allowed_mutations": ["x"],
            "mutation_channels": ["csharp"],
            "unresolved_bindings": ["target"],
        }
        self.assertIn("Unresolved bindings must clear allowed mutations", validate_effective_harness(document))

    def test_personal_full_control_enforces_selected_profile(self) -> None:
        document = build("csharp-local-fix")
        self.assertEqual(document["route_id"], "csharp-local-fix")
        self.assertEqual(document["execution_profile"], "personal_full_control")
        self.assertEqual(document["permission"]["mutate"], "allowed")
        self.assertFalse(document["human_approval"]["required"])

    def test_conditional_approval_blocks_direct_mutation_when_triggered(self) -> None:
        document = build("csharp-local-fix", request={"requires_human_approval": True})
        self.assertEqual(document["permission"]["mutate"], "approval-dependent")
        self.assertEqual(document["allowed_mutations"], [])
        self.assertTrue(document["human_approval"]["required"])

    def test_request_bound_contract_stays_non_mutating_until_channel_resolves(self) -> None:
        unresolved = build("performance-experiment")
        resolved = build("performance-experiment", request={"mutation_channels": ["shader"]})
        self.assertEqual(unresolved["permission"]["mutate"], "approval-dependent")
        self.assertEqual(unresolved["allowed_mutations"], [])
        self.assertEqual(resolved["permission"]["mutate"], "allowed")
        self.assertEqual(resolved["mutation_channels"], ["shader"])

    def test_team_safe_import_allows_package_only_runtime_mutation(self) -> None:
        document = build("safe-import-integration")
        self.assertEqual(document["execution_profile"], "team_safe_import")
        self.assertEqual(document["mutation_channels"], ["package"])
        self.assertEqual(document["permission"]["mutate"], "allowed")
        self.assertIn("staging_import", document["allowed_mutations"])

    def test_generic_planning_profile_never_grants_direct_mutation(self) -> None:
        document = build(
            "visual-direction",
            profile="generic_planning",
            request={"mutation_channels": ["material"], "human_approval_granted": True},
        )
        self.assertEqual(document["permission"]["mutate"], "approval-dependent")
        self.assertEqual(document["allowed_mutations"], [])

    def test_r3_project_asset_channel_requires_approval(self) -> None:
        document = build("asset-data-change", request={"mutation_channels": ["material"]})
        self.assertEqual(document["permission"]["mutate"], "approval-dependent")
        self.assertTrue(document["human_approval"]["required"])

    def test_legacy_harness_projection_authority_is_removed(self) -> None:
        self.assertFalse((ROOT / "Tools/HarnessProjection").exists())
        self.assertFalse((ROOT / "Tests/HarnessProjection").exists())
        validator = (ROOT / "Tools/validate_all.py").read_text(encoding="utf-8")
        self.assertNotIn("Tools/HarnessProjection", validator)
        self.assertNotIn("Tests/HarnessProjection", validator)


if __name__ == "__main__":
    unittest.main()
