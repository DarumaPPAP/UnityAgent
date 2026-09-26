from __future__ import annotations

import unittest

from Eval.Regression.compare_specialist_promotion import compare_promotion
from Eval.Tests.test_specialist_three_way import arm


def recorded_arm(name: str, *, specialist: bool) -> dict:
    value = arm(name, bytes_count=500 if specialist else 400, specialist=specialist)
    if name == "B":
        value["manifest"]["materialized_context"]["selected_refs"]["skill"] = {"resolved_path": ".agents/skills/unity-rendering/SKILL.md"}
    value["review"] = {"wrong_assumptions": 0, "tool_selection_errors": 0, "approval_violations": 0, "unsupported_claims": 0, "trace_legibility": "clear", "latency_ms": 1200}
    return value


class SpecialistPromotionComparisonTests(unittest.TestCase):
    def test_real_run_contract_is_required_without_automatic_promotion(self) -> None:
        arms = {"A_unity_agent": recorded_arm("A", specialist=False), "B_skill_tool": recorded_arm("B", specialist=False), "C_specialist": recorded_arm("C", specialist=True)}

        report = compare_promotion(arms, {"specialist:project_fact:unity_version:ProjectVersion.txt"})

        self.assertTrue(report["candidate_evidence_valid"])
        self.assertEqual(report["promotion_decision"], "requires_human_review")
        self.assertEqual(report["arms"]["C_specialist"]["selected_bytes"], 500)

    def test_missing_review_or_context_receipt_fails_closed(self) -> None:
        arms = {"A_unity_agent": recorded_arm("A", specialist=False), "B_skill_tool": recorded_arm("B", specialist=False), "C_specialist": recorded_arm("C", specialist=True)}
        arms["B_skill_tool"].pop("review")
        with self.assertRaisesRegex(ValueError, "review"):
            compare_promotion(arms, set())

        arms["B_skill_tool"] = recorded_arm("B", specialist=False)
        arms["C_specialist"]["result"]["results"][0]["provider_result"]["received_context_id"] = "wrong"
        with self.assertRaisesRegex(ValueError, "Context Receipt"):
            compare_promotion(arms, set())

    def test_unsupported_claim_blocks_candidate_evidence(self) -> None:
        arms = {"A_unity_agent": recorded_arm("A", specialist=False), "B_skill_tool": recorded_arm("B", specialist=False), "C_specialist": recorded_arm("C", specialist=True)}
        arms["C_specialist"]["review"]["unsupported_claims"] = 1

        report = compare_promotion(arms, set())

        self.assertFalse(report["candidate_evidence_valid"])
        self.assertEqual(report["promotion_decision"], "requires_human_review")


if __name__ == "__main__":
    unittest.main()
