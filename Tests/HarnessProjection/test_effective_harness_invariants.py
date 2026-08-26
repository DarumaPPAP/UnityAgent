"""Effective Harness cross-file invariant tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/HarnessProjection"))
from effective_harness import build_effective_harness, validate_effective_harness  # noqa: E402


class EffectiveHarnessInvariantTests(unittest.TestCase):
    def test_all_task_contracts_resolve_without_invariant_errors(self) -> None:
        for path in sorted((ROOT / ".ai/harness/task-contracts").glob("*.yaml")):
            if path.name == "task-contract.schema.yaml":
                continue
            document = build_effective_harness(ROOT, path.relative_to(ROOT).as_posix())
            self.assertEqual(validate_effective_harness(document), [], path.name)

    def test_r0_always_blocks_mutation(self) -> None:
        document = {"risk_level": "R0", "permission": {"mutate": "allowed"}, "allowed_mutations": []}
        self.assertIn("R0 must block mutation", validate_effective_harness(document))

    def test_prohibited_mutation_wins_over_allowed_mutation(self) -> None:
        document = {
            "risk_level": "R1",
            "permission": {"mutate": "allowed"},
            "allowed_mutations": ["x"],
            "prohibited_mutations": ["x"],
            "mutation_channels": ["csharp"],
        }
        self.assertIn("Mutation cannot be both allowed and prohibited", validate_effective_harness(document))

    def test_unresolved_binding_clears_direct_mutation(self) -> None:
        document = {
            "risk_level": "R1",
            "permission": {"mutate": "approval-dependent"},
            "allowed_mutations": ["x"],
            "mutation_channels": ["csharp"],
            "unresolved_bindings": ["target"],
        }
        self.assertIn("Unresolved bindings must clear allowed mutations", validate_effective_harness(document))

    def test_r1_conditional_does_not_require_approval_by_default(self) -> None:
        document = build_effective_harness(
            ROOT,
            ".ai/harness/task-contracts/csharp-local-fix.yaml",
        )
        self.assertEqual(document["permission"]["mutate"], "allowed")
        self.assertFalse(document["human_approval"]["required"])
        self.assertFalse(any(gate["id"] == "human_approval" for gate in document["human_gates"]))

    def test_r1_conditional_blocks_when_request_triggers_approval(self) -> None:
        document = build_effective_harness(
            ROOT,
            ".ai/harness/task-contracts/csharp-local-fix.yaml",
            request={"requires_human_approval": True},
        )
        self.assertEqual(document["permission"]["mutate"], "approval-dependent")
        self.assertEqual(document["allowed_mutations"], [])
        self.assertTrue(document["human_approval"]["required"])

    def test_r2_destructive_change_requires_approval(self) -> None:
        document = build_effective_harness(
            ROOT,
            ".ai/harness/task-contracts/shader-change.yaml",
            request={"destructive_change": True},
        )
        self.assertEqual(document["permission"]["mutate"], "approval-dependent")
        self.assertTrue(document["human_approval"]["required"])

    def test_r3_project_asset_channel_requires_approval(self) -> None:
        document = build_effective_harness(
            ROOT,
            ".ai/harness/task-contracts/asset-data-change.yaml",
            request={"mutation_channels": ["material"]},
        )
        self.assertEqual(document["permission"]["mutate"], "approval-dependent")
        self.assertTrue(document["human_approval"]["required"])

    def test_request_bound_performance_contract_stays_non_mutating_until_channel_resolves(self) -> None:
        unresolved = build_effective_harness(
            ROOT,
            ".ai/harness/task-contracts/performance-experiment.yaml",
        )
        resolved = build_effective_harness(
            ROOT,
            ".ai/harness/task-contracts/performance-experiment.yaml",
            request={"mutation_channels": ["shader"]},
        )
        self.assertEqual(unresolved["permission"]["mutate"], "approval-dependent")
        self.assertEqual(unresolved["allowed_mutations"], [])
        self.assertEqual(resolved["permission"]["mutate"], "allowed")
        self.assertEqual(resolved["mutation_channels"], ["shader"])


if __name__ == "__main__":
    unittest.main()
