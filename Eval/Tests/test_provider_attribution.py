from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Eval.Attribution.attribution import (
    AttributionError,
    build_provider_eval_record,
    classify_provider_failure,
)
from Eval.Behavior.runtime_adapter import adapt_execution_result


class ProviderAttributionTests(unittest.TestCase):
    def evidence(
        self,
        *,
        failure_class=None,
        completion="verified",
        observation_state="observed",
        status="passed",
    ):
        return {
            "schema_version": "1.1",
            "evidence_id": "evidence-1",
            "run_id": "run-1",
            "provider_ref": "player_runtime",
            "capability": "player.observe",
            "completion": completion,
            "observation_state": observation_state,
            "failure_class": failure_class,
            "status": status,
            "environment": {
                "profile_hint": "PLAYER_UNAVAILABLE"
                if completion == "blocked_by_environment"
                else "FULL",
                "binding_fingerprint": "a" * 64,
                "unity_version": "6000.3.15f1",
                "requested_target": "Switch",
            },
            "safety_strength": 4,
            "evidence_strength": 4,
        }

    def build(self, evidence):
        return build_provider_eval_record(
            eval_id="eval-1",
            source_execution_result_ref="runtime/result.json",
            evidence=evidence,
        )

    def validate_eval_record(self, value):
        schema = yaml.safe_load(
            (ROOT / "Eval/Attribution/eval-record.schema.yaml").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(value)

    def test_provider_unavailable_is_runtime_infrastructure_not_agent_regression(self):
        result = self.build(
            self.evidence(
                failure_class="unavailable",
                completion="blocked_by_environment",
                observation_state="not_observed",
                status="unavailable",
            )
        )
        self.assertEqual(result["failure_class"], "runtime_tool_unavailable")
        self.assertEqual(result["failure_attribution"], "runtime_infrastructure")
        self.assertEqual(
            result["provider_failure_attribution"],
            "environment_or_provider",
        )
        self.assertFalse(result["quality_denominator_eligible"])
        self.validate_eval_record(result)

    def test_timeout_is_provider_infrastructure_and_excluded(self):
        result = self.build(
            self.evidence(
                failure_class="timeout",
                completion="blocked_by_environment",
                observation_state="not_observed",
                status="unavailable",
            )
        )
        self.assertEqual(result["failure_class"], "runtime_timeout")
        self.assertEqual(
            result["provider_failure_attribution"],
            "provider_infrastructure",
        )
        self.assertFalse(result["quality_denominator_eligible"])

    def test_approval_failure_is_distinct_from_provider_unavailable(self):
        approval = self.build(
            self.evidence(
                failure_class="blocked_by_approval",
                completion="implemented_unverified",
                observation_state="not_observed",
                status="failed",
            )
        )
        unavailable = self.build(
            self.evidence(
                failure_class="unavailable",
                completion="blocked_by_environment",
                observation_state="not_observed",
                status="unavailable",
            )
        )
        self.assertEqual(approval["failure_class"], "runtime_permission_denied")
        self.assertEqual(approval["failure_attribution"], "policy_or_permission")
        self.assertNotEqual(
            approval["provider_failure_attribution"],
            unavailable["provider_failure_attribution"],
        )

    def test_not_observed_is_unavailable_evidence_and_excluded_from_denominator(self):
        result = self.build(
            self.evidence(
                failure_class="not_observed",
                completion="implemented_unverified",
                observation_state="not_observed",
                status="unverified",
            )
        )
        self.assertEqual(result["failure_class"], "unavailable_required_evidence")
        self.assertEqual(result["failure_attribution"], "unavailable_evidence")
        self.assertFalse(result["quality_denominator_eligible"])

    def test_observed_test_failure_is_not_preclassified_as_agent_regression(self):
        result = self.build(
            self.evidence(
                failure_class="observed_test_failure",
                completion="verified",
                observation_state="observed",
                status="failed",
            )
        )
        self.assertIsNone(result["failure_class"])
        self.assertEqual(result["failure_attribution"], "none")
        self.assertEqual(
            result["provider_failure_attribution"],
            "observed_product_failure",
        )
        self.assertTrue(result["quality_denominator_eligible"])
        self.validate_eval_record(result)

    def test_partial_verified_observation_remains_observed_without_failure(self):
        result = self.build(
            self.evidence(
                failure_class=None,
                completion="partial_verified",
                observation_state="observed",
                status="passed",
            )
        )
        self.assertEqual(result["completion"], "partial_verified")
        self.assertIsNone(result["failure_class"])
        self.assertTrue(result["quality_denominator_eligible"])

    def test_observed_product_failure_without_observed_evidence_is_rejected(self):
        with self.assertRaises(AttributionError):
            classify_provider_failure(
                "observed_test_failure",
                observation_state="not_observed",
            )

    def test_unknown_provider_failure_class_fails_closed(self):
        evidence = self.evidence(
            failure_class="made_up_failure",
            completion="implemented_unverified",
            observation_state="not_observed",
            status="failed",
        )
        with self.assertRaises(AttributionError):
            self.build(evidence)

    def test_generic_eval_adapter_accepts_execution_result_v11_without_text_reconstruction(self):
        execution = {
            "schema_version": "1.1",
            "run_id": "run-1",
            "step_id": "step-1",
            "status": "passed",
            "runtime_failure": None,
            "changed_paths": {"observation_state": "not_observed", "paths": []},
            "gate_outcomes": [],
            "tool_identity": {},
            "definition_fingerprint": {},
            "evidence_refs": ["evidence-1"],
            "capability_outcomes": [
                {
                    "capability": "player.observe",
                    "provider_ref": "player_runtime",
                    "completion": "blocked_by_environment",
                    "status": "unavailable",
                    "failure_class": "unavailable",
                    "observation_state": "not_observed",
                    "evidence_refs": ["evidence-1"],
                    "environment_profile": "PLAYER_UNAVAILABLE",
                    "safety_strength": 4,
                    "evidence_strength": 4,
                }
            ],
        }
        projection = adapt_execution_result(
            execution,
            eval_id="eval-generic",
            source_execution_result_ref="runtime/result.json",
        )
        self.assertEqual(projection["run_id"], "run-1")
        self.assertEqual(projection["eval_record"]["schema_version"], "1.1")
        self.assertEqual(projection["eval_record"]["evidence_refs"], ["evidence-1"])


if __name__ == "__main__":
    unittest.main()
