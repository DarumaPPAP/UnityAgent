from __future__ import annotations

import copy
import unittest
from pathlib import Path

import yaml

from Eval.Rebaseline.baseline_freeze import BaselineFreezeError, validate_baseline_freeze


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "Eval/Rebaseline/Baselines/phase9-baseline-20260830-09.yaml"


def frozen_baseline() -> dict:
    value = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise AssertionError("frozen baseline manifest must be a YAML mapping")
    return value


class BaselineFreezeTests(unittest.TestCase):
    def test_checked_in_frozen_baseline_is_valid(self):
        value = frozen_baseline()
        validate_baseline_freeze(value)
        self.assertEqual(value["accepted_run"]["run_id"], "phase9-baseline-20260830-09")
        self.assertEqual(value["source"]["revision"], "08d915886a24689e40cc74b1d32277bb80a3aa5a")
        self.assertEqual(value["runtime"]["model"], "gpt-5.6-luna")
        self.assertEqual(value["runtime"]["reasoning_effort"], "xhigh")
        self.assertEqual(value["quality"]["regression_pass_rate"], 1.0)

    def test_historical_replay_zero_quality_denominator_is_transparently_frozen_as_informational(self):
        value = frozen_baseline()
        self.assertEqual(value["historical_replay"]["quality_denominator_eligible_count"], 0)
        self.assertEqual(value["historical_replay"]["quality_semantics"], "namespace_coverage_only")
        validate_baseline_freeze(value)

    def test_missing_historical_namespace_is_rejected(self):
        value = frozen_baseline()
        value["historical_replay"]["observed_namespaces"] = ["ARCH", "NAMING", "MUTATION"]
        with self.assertRaises(BaselineFreezeError):
            validate_baseline_freeze(value)

    def test_non_four_of_four_quality_is_rejected(self):
        value = frozen_baseline()
        value["quality"]["quality_denominator"] = 3
        with self.assertRaises(BaselineFreezeError):
            validate_baseline_freeze(value)

    def test_missing_definition_fingerprint_is_rejected(self):
        value = frozen_baseline()
        del value["definition_fingerprints"]["GOLDEN-NAMING-001"]
        with self.assertRaises(BaselineFreezeError):
            validate_baseline_freeze(value)

    def test_provenance_must_point_to_the_accepted_run(self):
        value = frozen_baseline()
        value["provenance"]["rebaseline_summary_ref"] = (
            "Artifacts/ProductionSmoke/another-run/rebaseline-summary.json"
        )
        with self.assertRaises(BaselineFreezeError):
            validate_baseline_freeze(value)

    def test_freeze_id_must_match_accepted_run(self):
        value = copy.deepcopy(frozen_baseline())
        value["freeze_id"] = "different-run-freeze"
        with self.assertRaises(BaselineFreezeError):
            validate_baseline_freeze(value)


if __name__ == "__main__":
    unittest.main()
