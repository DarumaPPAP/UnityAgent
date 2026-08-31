from __future__ import annotations

import copy
import unittest
from pathlib import Path

import yaml

from Eval.Regression.baseline_comparator import (
    BaselineComparisonError,
    build_baseline_comparison,
    validate_baseline_comparison,
)
from Eval.Rebaseline.rebaseline import EXPECTED_CASES, build_rebaseline_summary

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml"


def _baseline() -> dict:
    value = yaml.safe_load(BASELINE_PATH.read_text(encoding="utf-8")) or {}
    assert isinstance(value, dict)
    return value


def _passed_result(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "status": "passed",
        "observation_state": "observed",
        "quality_denominator_eligible": True,
        "failure_details": [],
        "naming_findings": [],
    }


def _passed_eval_summary() -> dict:
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
        "results": [_passed_result(task_id) for task_id in EXPECTED_CASES],
    }


def _candidate(
    *,
    eval_summary: dict | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    codex_version: str | None = None,
    fingerprints: dict | None = None,
) -> dict:
    baseline = _baseline()
    return build_rebaseline_summary(
        eval_summary or _passed_eval_summary(),
        run_id="phase10-candidate",
        source_revision="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        model=model or baseline["runtime"]["model"],
        reasoning_effort=reasoning_effort or baseline["runtime"]["reasoning_effort"],
        codex_version=codex_version or baseline["runtime"]["codex_version"],
        definition_fingerprints=(
            copy.deepcopy(fingerprints)
            if fingerprints is not None
            else copy.deepcopy(baseline["definition_fingerprints"])
        ),
        historical_replay=None,
    )


class Phase10BaselineComparatorTests(unittest.TestCase):
    def test_clean_candidate_passes_without_historical_replay(self):
        baseline = _baseline()
        comparison = build_baseline_comparison(baseline, _candidate())
        self.assertEqual(comparison["gate"]["decision"], "PASS")
        self.assertEqual(comparison["comparability"]["status"], "comparable_with_drift")
        self.assertEqual(comparison["baseline"]["freeze_id"], baseline["freeze_id"])
        self.assertEqual(comparison["quality_delta"]["candidate"]["quality_passed"], 4)
        self.assertEqual(comparison["quality_delta"]["candidate"]["regression_pass_rate"], 1.0)
        validate_baseline_comparison(comparison)

    def test_context_revision_drift_remains_comparable(self):
        candidate = _candidate()
        candidate["definition_fingerprints"]["GOLDEN-NAMING-001"]["context_revision"] = (
            "sha256:candidate-context"
        )
        comparison = build_baseline_comparison(_baseline(), candidate)
        self.assertEqual(comparison["comparability"]["status"], "comparable_with_drift")
        self.assertEqual(comparison["gate"]["decision"], "PASS")
        self.assertTrue(
            any(
                item["field"] == "context_revision"
                for item in comparison["comparability"]["informational_drift"]
            )
        )

    def test_codex_cli_drift_is_informational(self):
        comparison = build_baseline_comparison(
            _baseline(),
            _candidate(codex_version="codex-cli candidate"),
        )
        self.assertEqual(comparison["comparability"]["status"], "comparable_with_drift")
        self.assertEqual(comparison["gate"]["decision"], "PASS")

    def test_model_change_requires_rebaseline(self):
        comparison = build_baseline_comparison(
            _baseline(),
            _candidate(model="gpt-5.6-sol"),
        )
        self.assertEqual(comparison["comparability"]["status"], "not_comparable")
        self.assertEqual(comparison["gate"]["decision"], "REBASELINE_REQUIRED")
        self.assertTrue(
            any(
                item["scope"] == "runtime" and item["field"] == "model"
                for item in comparison["comparability"]["blocking_drift"]
            )
        )

    def test_policy_definition_change_requires_rebaseline(self):
        candidate = _candidate()
        candidate["definition_fingerprints"]["GOLDEN-ARCH-001"]["policy_revision"] = (
            "sha256:candidate-policy"
        )
        comparison = build_baseline_comparison(_baseline(), candidate)
        self.assertEqual(comparison["comparability"]["status"], "not_comparable")
        self.assertEqual(comparison["gate"]["decision"], "REBASELINE_REQUIRED")

    def test_runtime_timeout_is_block_inconclusive_not_agent_regression(self):
        eval_summary = _passed_eval_summary()
        eval_summary["results"][-1] = {
            "task_id": EXPECTED_CASES[-1],
            "status": "failed",
            "observation_state": "not_observed",
            "quality_denominator_eligible": False,
            "failure_details": ["runtime_timeout"],
            "naming_findings": [],
        }
        eval_summary["overall_passed"] = 3
        eval_summary["overall_failed"] = 1
        eval_summary["quality_denominator"] = 3
        eval_summary["quality_passed"] = 3
        eval_summary["regression_pass_rate"] = 1.0
        eval_summary["not_observed_count"] = 1
        eval_summary["failure_counts"] = {"runtime_timeout": 1}

        comparison = build_baseline_comparison(
            _baseline(),
            _candidate(eval_summary=eval_summary),
        )
        self.assertEqual(comparison["gate"]["decision"], "BLOCK_INCONCLUSIVE")
        self.assertIn("runtime_timeout", comparison["taxonomy"]["active_failure_classes"])
        self.assertNotIn(
            "agent_behavior_regression",
            comparison["taxonomy"]["active_failure_classes"],
        )

    def test_observed_agent_failure_is_block_regression(self):
        eval_summary = _passed_eval_summary()
        eval_summary["results"][1] = {
            "task_id": EXPECTED_CASES[1],
            "status": "failed",
            "observation_state": "observed",
            "quality_denominator_eligible": True,
            "failure_details": ["routing_miss"],
            "naming_findings": [],
        }
        eval_summary["overall_passed"] = 3
        eval_summary["overall_failed"] = 1
        eval_summary["quality_passed"] = 3
        eval_summary["regression_pass_rate"] = 0.75
        eval_summary["failure_counts"] = {"routing_miss": 1}

        comparison = build_baseline_comparison(
            _baseline(),
            _candidate(eval_summary=eval_summary),
        )
        self.assertEqual(comparison["gate"]["decision"], "BLOCK_REGRESSION")
        self.assertIn(
            "agent_behavior_regression",
            comparison["taxonomy"]["active_failure_classes"],
        )
        self.assertTrue(comparison["cases"][EXPECTED_CASES[1]]["regression"])

    def test_missing_candidate_fingerprint_is_block_inconclusive(self):
        fingerprints = copy.deepcopy(_baseline()["definition_fingerprints"])
        fingerprints.pop("GOLDEN-EVIDENCE-001")
        comparison = build_baseline_comparison(
            _baseline(),
            _candidate(fingerprints=fingerprints),
        )
        self.assertEqual(comparison["comparability"]["status"], "insufficient_evidence")
        self.assertEqual(comparison["gate"]["decision"], "BLOCK_INCONCLUSIVE")
        self.assertIn(
            "definition_fingerprints.GOLDEN-EVIDENCE-001",
            comparison["comparability"]["missing_evidence"],
        )

    def test_saved_pass_report_cannot_hide_lower_quality(self):
        comparison = build_baseline_comparison(_baseline(), _candidate())
        comparison["quality_delta"]["candidate"]["quality_passed"] = 3
        comparison["quality_delta"]["quality_passed_delta"] = -1
        with self.assertRaises(BaselineComparisonError):
            validate_baseline_comparison(comparison)

    def test_saved_pass_report_cannot_hide_unobserved_case(self):
        comparison = build_baseline_comparison(_baseline(), _candidate())
        case = comparison["cases"]["GOLDEN-EVIDENCE-001"]
        case["candidate_observation_state"] = "not_observed"
        with self.assertRaises(BaselineComparisonError):
            validate_baseline_comparison(comparison)


if __name__ == "__main__":
    unittest.main()
