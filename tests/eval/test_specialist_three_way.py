from __future__ import annotations

import unittest

from eval.regression.compare_specialist_three_way import compare


def arm(name: str, *, bytes_count: int, specialist: bool, irrelevant: bool = False) -> dict:
    run_id = f"run-{name}"
    context_id = f"ctx-{name}"
    items = ([{"type": "project_fact", "key": "unity_version", "source": "ProjectVersion.txt"}]
             if specialist else [])
    if irrelevant:
        items.append({"type": "platform_fact", "key": "audio", "source": "AudioSettings"})
    return {"task_id": "same-camera-capture", "manifest": {"run_id": run_id,
        "budget_report": {"selected_artifacts": 4 + len(items), "selected_utf8_bytes": bytes_count,
            "estimated_tokens": (bytes_count + 2) // 3, "decision": "within_budget"},
        "materialized_context": {"context_id": context_id, "context_fingerprint": {"value": f"sha256:{name}"}, "selected_refs": {"policy": []},
            "resolved_bindings": {}, "specialist_context": {"items": items} if specialist else None}},
        "result": {"run_id": run_id, "status": "completed", "handoff": {"context_id": context_id, "context_fingerprint": f"sha256:{name}"},
            "evidence_refs": [f"{run_id}-evidence"], "results": [{"attempts": [{"status": "passed"}],
                "receipt_integrity": "verified" if specialist else None,
                "provider_result": {"received_context_id": context_id, "received_context_fingerprint": f"sha256:{name}"} if specialist else {}}]},
        "evidence": [{"run_id": run_id, "evidence_id": f"{run_id}-evidence",
            "verification_status": "passed", "required_evidence": ["visual_capture"],
            "observed_evidence": ["visual_capture"]}]}


class SpecialistThreeWayTests(unittest.TestCase):
    def test_requires_smaller_relevant_context_and_complete_durable_evidence(self) -> None:
        arms = {"A_existing": arm("A", bytes_count=400, specialist=False),
            "B_naive": arm("B", bytes_count=700, specialist=True, irrelevant=True),
            "C_filtered": arm("C", bytes_count=500, specialist=True)}
        relevant = {"specialist:project_fact:unity_version:ProjectVersion.txt"}
        self.assertTrue(compare(arms, relevant)["comparison_passed"])
        arms["C_filtered"]["evidence"][0]["observed_evidence"] = []
        self.assertFalse(compare(arms, relevant)["comparison_passed"])
        arms["C_filtered"]["evidence"][0]["observed_evidence"] = ["visual_capture"]
        arms["C_filtered"]["result"]["results"][0]["provider_result"]["received_context_id"] = "forged"
        self.assertFalse(compare(arms, relevant)["comparison_passed"])
        arms["C_filtered"]["result"]["evidence_refs"] = []
        with self.assertRaisesRegex(ValueError, "durable Evidence"):
            compare(arms, relevant)



import unittest

from eval.regression.compare_specialist_promotion import compare_promotion


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
