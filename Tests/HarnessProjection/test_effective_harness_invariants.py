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
        document = {"risk_level": "R1", "permission": {"mutate": "allowed"}, "allowed_mutations": ["x"], "prohibited_mutations": ["x"]}
        self.assertIn("Mutation cannot be both allowed and prohibited", validate_effective_harness(document))

    def test_unresolved_binding_clears_direct_mutation(self) -> None:
        document = {"risk_level": "R1", "permission": {"mutate": "approval-dependent"}, "allowed_mutations": ["x"], "unresolved_bindings": ["target"]}
        self.assertIn("Unresolved bindings must clear allowed mutations", validate_effective_harness(document))
