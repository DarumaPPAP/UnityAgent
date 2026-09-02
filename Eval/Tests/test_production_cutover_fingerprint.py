from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

from Eval.Regression.baseline_comparator import build_baseline_comparison
from Eval.Rebaseline.rebaseline import EXPECTED_CASES, build_rebaseline_summary

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml"
CUTOVER_REVISIONS = {
    "architecture_version": "v4.0",
    "runtime_profile_revision": "runtime-profiles-v1",
    "tool_schema_revision": "production-tool-runtime-v1",
    "evidence_schema_revision": "1.2",
    "eval_contract_revision": "1.2",
}


def _passed_eval_summary() -> dict:
    results = [
        {
            "task_id": task_id,
            "status": "passed",
            "observation_state": "observed",
            "quality_denominator_eligible": True,
            "failure_details": [],
            "naming_findings": [],
        }
        for task_id in EXPECTED_CASES
    ]
    return {
        "schema_version": "1.0",
        "total": len(results),
        "overall_passed": len(results),
        "overall_failed": 0,
        "quality_denominator": len(results),
        "quality_passed": len(results),
        "regression_pass_rate": 1.0,
        "not_observed_count": 0,
        "failure_counts": {},
        "results": results,
    }


class ProductionCutoverFingerprintTests(unittest.TestCase):
    def test_cutover_definition_drift_requires_explicit_rebaseline(self):
        baseline = yaml.safe_load(BASELINE_PATH.read_text(encoding="utf-8"))
        fingerprints = copy.deepcopy(baseline["definition_fingerprints"])
        for task_id in EXPECTED_CASES:
            fingerprints[task_id].update(CUTOVER_REVISIONS)
        candidate = build_rebaseline_summary(
            _passed_eval_summary(),
            run_id="production-cutover-candidate",
            source_revision="cccccccccccccccccccccccccccccccccccccccc",
            model=baseline["runtime"]["model"],
            reasoning_effort=baseline["runtime"]["reasoning_effort"],
            codex_version=baseline["runtime"]["codex_version"],
            definition_fingerprints=fingerprints,
            historical_replay=None,
        )
        comparison = build_baseline_comparison(baseline, candidate)
        self.assertEqual(comparison["comparability"]["status"], "not_comparable")
        self.assertEqual(comparison["gate"]["decision"], "REBASELINE_REQUIRED")
        drift_fields = {item["field"] for item in comparison["comparability"]["blocking_drift"]}
        self.assertTrue(set(CUTOVER_REVISIONS).issubset(drift_fields))
        self.assertEqual(baseline["definition_fingerprints"], yaml.safe_load(BASELINE_PATH.read_text(encoding="utf-8"))["definition_fingerprints"])


if __name__ == "__main__":
    unittest.main()
