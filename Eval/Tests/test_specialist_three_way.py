from __future__ import annotations

import unittest

from Eval.Regression.compare_specialist_three_way import compare


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
        "materialized_context": {"context_id": context_id, "selected_refs": {"policy": []},
            "resolved_bindings": {}, "specialist_context": {"items": items} if specialist else None}},
        "result": {"run_id": run_id, "status": "completed", "handoff": {"context_id": context_id},
            "evidence_refs": [f"{run_id}-evidence"], "results": [{"attempts": [{"status": "passed"}]}]},
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
        arms["C_filtered"]["result"]["evidence_refs"] = []
        with self.assertRaisesRegex(ValueError, "durable Evidence"):
            compare(arms, relevant)


if __name__ == "__main__":
    unittest.main()
