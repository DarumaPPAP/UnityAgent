from __future__ import annotations

import copy
import unittest

from Eval.Rebaseline.rebaseline import (
    EXPECTED_CASES,
    RebaselineError,
    build_rebaseline_summary,
    validate_rebaseline_summary,
)


FINGERPRINT = {
    "schema_version": "1.0",
    "architecture_version": "3.1",
    "policy_revision": "policy-test",
    "prompt_revision": "prompt-test",
    "context_revision": "context-test",
    "graph_revision": "graph-test",
    "runtime_profile_revision": "runtime-test",
    "tool_schema_revision": "tool-test",
    "checkpoint_schema_revision": "checkpoint-test",
    "evidence_schema_revision": "evidence-test",
    "eval_contract_revision": "eval-test",
}


def passed_result(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "status": "passed",
        "observation_state": "observed",
        "quality_denominator_eligible": True,
        "failure_details": [],
        "naming_findings": [],
    }


def passed_eval_summary() -> dict:
    return {
        "schema_version": "1.0",
        "total": 4,
        "overall_passed": 4,
        "overall_failed": 0,
        "quality_denominator": 4,
        "quality_passed": 4,
        "regression_pass_rate": 1.0,
        "not_observed_count": 0,
        "failure_counts": {},
        "results": [passed_result(task_id) for task_id in EXPECTED_CASES],
    }


def fingerprints() -> dict:
    return {task_id: copy.deepcopy(FINGERPRINT) for task_id in EXPECTED_CASES}


class RebaselineTests(unittest.TestCase):
    def build(self, eval_summary: dict, historical: dict | None):
        return build_rebaseline_summary(
            eval_summary,
            run_id="rebaseline-test",
            source_revision="deadbeef",
            model="gpt-5.6-sol",
            reasoning_effort="high",
            codex_version="codex-test",
            definition_fingerprints=fingerprints(),
            historical_replay=historical,
        )

    def test_four_passes_and_historical_coverage_are_baseline_ready(self):
        historical = {
            "schema_version": "1.0",
            "case_count": 6,
            "observed_namespaces": ["ARCH", "NAMING", "MUTATION", "EVIDENCE"],
            "quality_denominator_eligible_count": 2,
        }
        summary = self.build(passed_eval_summary(), historical)
        self.assertEqual(summary["status"], "baseline_ready")
        self.assertTrue(summary["baseline"]["eligible"])
        self.assertEqual(summary["quality"]["quality_denominator"], 4)
        self.assertEqual(summary["quality"]["quality_passed"], 4)
        self.assertEqual(summary["quality"]["regression_pass_rate"], 1.0)
        self.assertTrue(all(value == 0 for value in summary["taxonomy"]["counts"].values()))
        validate_rebaseline_summary(summary)

    def test_clean_smoke_waits_for_historical_replay_without_rerunning_taxonomy(self):
        summary = self.build(passed_eval_summary(), None)
        self.assertEqual(summary["status"], "smoke_passed_pending_historical")
        self.assertFalse(summary["baseline"]["eligible"])
        self.assertEqual(summary["historical_replay"]["status"], "pending")
        self.assertEqual(summary["baseline"]["reasons"], ["historical replay coverage is pending"])

    def test_runtime_timeout_is_attributed_once_and_excluded_from_quality_denominator(self):
        eval_summary = passed_eval_summary()
        eval_summary["results"][-1] = {
            "task_id": EXPECTED_CASES[-1],
            "status": "failed",
            "observation_state": "not_observed",
            "quality_denominator_eligible": False,
            "failure_details": ["runtime_timeout"],
            "naming_findings": [],
        }
        eval_summary["failure_counts"] = {"runtime_timeout": 1}
        summary = self.build(eval_summary, None)
        self.assertEqual(summary["taxonomy"]["counts"]["runtime_timeout"], 1)
        self.assertEqual(summary["taxonomy"]["counts"]["agent_behavior_regression"], 0)
        self.assertEqual(summary["taxonomy"]["attribution_counts"]["runtime_infrastructure"], 1)
        self.assertEqual(summary["quality"]["quality_denominator"], 3)
        self.assertEqual(summary["quality"]["quality_passed"], 3)
        self.assertEqual(summary["status"], "not_eligible")

    def test_observed_failure_is_one_agent_regression_with_diagnostics_kept_separate(self):
        eval_summary = passed_eval_summary()
        eval_summary["results"][0] = {
            "task_id": EXPECTED_CASES[0],
            "status": "failed",
            "observation_state": "observed",
            "quality_denominator_eligible": True,
            "failure_details": ["routing_miss", "policy_violation"],
            "naming_findings": [],
        }
        eval_summary["failure_counts"] = {"routing_miss": 1, "policy_violation": 1}
        summary = self.build(eval_summary, None)
        case = summary["cases"][EXPECTED_CASES[0]]
        self.assertEqual(case["taxonomy_failure_classes"], ["agent_behavior_regression"])
        self.assertEqual(case["diagnostic_failure_details"], ["policy_violation", "routing_miss"])
        self.assertEqual(summary["taxonomy"]["counts"]["agent_behavior_regression"], 1)
        self.assertEqual(summary["diagnostics"]["failure_detail_counts"], {"policy_violation": 1, "routing_miss": 1})

    def test_not_observed_without_typed_non_agent_failure_is_rejected(self):
        eval_summary = passed_eval_summary()
        eval_summary["results"][0] = {
            "task_id": EXPECTED_CASES[0],
            "status": "failed",
            "observation_state": "not_observed",
            "quality_denominator_eligible": False,
            "failure_details": ["routing_miss"],
            "naming_findings": [],
        }
        with self.assertRaises(RebaselineError):
            self.build(eval_summary, None)


if __name__ == "__main__":
    unittest.main()
