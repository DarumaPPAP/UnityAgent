import json
import tempfile
import unittest
from pathlib import Path

import jsonschema
import yaml

from Eval.Attribution.attribution import build_eval_record
from Eval.Behavior.run_behavior_eval import evaluate_results
from Eval.Behavior.runtime_adapter import adapt_execution_result
from Eval.ChangeProposals.change_proposal import build_change_proposal
from Eval.GoldenContracts.build_contract import build_contract, runtime_task_projection
from Eval.Replay.historical_replay import replay

ROOT = Path(__file__).resolve().parents[2]


def fingerprint():
    return {
        "schema_version": "1.0",
        "architecture_version": "3.1",
        "policy_revision": "policy-a",
        "prompt_revision": "prompt-a",
        "context_revision": "context-a",
        "graph_revision": "graph-a",
        "runtime_profile_revision": "runtime-a",
        "tool_schema_revision": "tools-a",
        "checkpoint_schema_revision": "1.1",
        "evidence_schema_revision": "1.1",
        "eval_contract_revision": "eval-phase6",
    }


def execution_result(*, paths=None, failure=None):
    return {
        "schema_version": "1.0",
        "run_id": "run-1",
        "step_id": "step-1",
        "action_id": "action-1",
        "status": "failed" if failure else "passed",
        "started_at": None,
        "completed_at": None,
        "exit_code": None,
        "runtime_failure": failure,
        "changed_paths": {"observation_state": "observed", "paths": list(paths or [])},
        "gate_outcomes": [],
        "tool_identity": {
            "provider": "test",
            "model": "test-model",
            "model_revision": "1",
            "tool_manifest_hash": "manifest-a",
            "executor_profile": None,
            "execution_mode": "test",
        },
        "evidence_refs": ["evidence-1"],
        "telemetry_refs": [],
        "definition_fingerprint": fingerprint(),
    }


class Phase6EvalTests(unittest.TestCase):
    def test_canonical_datasets_are_present_and_self_contained(self):
        behavior = ROOT / "Eval" / "Datasets" / "Behavior"
        golden = ROOT / "Eval" / "Datasets" / "Golden"
        self.assertTrue((behavior / "suites.yaml").is_file())
        self.assertTrue((behavior / "execution-envelope.schema.yaml").is_file())
        self.assertTrue((behavior / "ProtocolFixtures" / "valid" / "execution-envelope.yaml").is_file())
        self.assertTrue((golden / "cases.yaml").is_file())
        self.assertTrue((golden / "context-budget-v1.yaml").is_file())
        self.assertFalse((ROOT / "Tests" / "BehaviorEval").exists())
        self.assertFalse((ROOT / "Tests" / "GoldenTasks").exists())

    def test_runtime_adapter_preserves_structured_changed_paths(self):
        source = execution_result(paths=["Assets/CameraDebugger.cs"])
        adapted = adapt_execution_result(
            source, eval_id="eval-1", source_execution_result_ref="runs/run-1/execution-result.json"
        )
        self.assertEqual(adapted["changed_paths"], source["changed_paths"])
        self.assertTrue(adapted["eval_record"]["quality_denominator_eligible"])
        self.assertIsNone(adapted["eval_record"]["failure_class"])

    def test_observed_mutation_noop_is_agent_regression(self):
        adapted = adapt_execution_result(
            execution_result(paths=[]), eval_id="eval-noop",
            source_execution_result_ref="runs/run-1/execution-result.json", expect_mutation=True,
        )
        record = adapted["eval_record"]
        self.assertEqual(record["failure_class"], "agent_behavior_regression")
        self.assertEqual(record["failure_attribution"], "agent_quality")
        self.assertEqual(record["observation_state"], "observed")
        self.assertTrue(record["quality_denominator_eligible"])

    def test_runtime_infrastructure_is_not_observed_or_denominator_eligible(self):
        failure = {
            "schema_version": "1.0", "failure_class": "runtime_timeout",
            "reason": "timeout", "retryable": True, "source_ref": "runtime",
            "observation_state": "not_observed",
        }
        record = adapt_execution_result(
            execution_result(paths=[], failure=failure), eval_id="eval-timeout",
            source_execution_result_ref="runs/run-1/execution-result.json",
        )["eval_record"]
        self.assertEqual(record["failure_attribution"], "runtime_infrastructure")
        self.assertEqual(record["observation_state"], "not_observed")
        self.assertFalse(record["quality_denominator_eligible"])

    def test_permission_denied_is_not_agent_quality(self):
        record = build_eval_record(
            eval_id="eval-permission", run_id="run-1",
            source_execution_result_ref="runs/run-1/execution-result.json",
            failure_class="runtime_permission_denied", observation_state="observed",
        )
        self.assertEqual(record["failure_attribution"], "policy_or_permission")
        self.assertEqual(record["observation_state"], "not_observed")
        self.assertFalse(record["quality_denominator_eligible"])

    def test_behavior_summary_uses_observed_quality_denominator(self):
        case_doc = yaml.safe_load((ROOT / "Eval" / "Datasets" / "Golden" / "cases.yaml").read_text(encoding="utf-8"))
        case = next(item for item in case_doc["cases"] if item["id"] == "GOLDEN-ARCH-001")
        expectation = case["expectation"]
        base = {
            "task_id": case["id"],
            "route": expectation["route"],
            "applied_policies": expectation.get("required_policies", []),
            "signals": expectation.get("required_signals", []),
            "gates": {gate: "passed" for gate in expectation.get("required_gates", [])},
            "knowledge": expectation.get("required_knowledge", []),
            "unresolved": [],
            "generated_artifacts": [],
            "outcome": "passed",
            "failure_types": [],
            "execution": {"mode": "actual_behavior", "observation_state": "observed"},
        }
        infra = dict(base)
        infra["failure_types"] = ["runtime_timeout"]
        infra["outcome"] = "unavailable"
        infra["execution"] = {"mode": "actual_behavior", "observation_state": "not_observed"}
        summary = evaluate_results({"results": [base, infra]})
        self.assertEqual(summary["quality_denominator"], 1)
        self.assertEqual(summary["quality_passed"], 1)
        self.assertEqual(summary["regression_pass_rate"], 1.0)
        self.assertEqual(summary["not_observed_count"], 1)

    def test_golden_contract_projection_and_no_runtime_leak(self):
        case_doc = yaml.safe_load((ROOT / "Eval" / "Datasets" / "Golden" / "cases.yaml").read_text(encoding="utf-8"))
        case = next(item for item in case_doc["cases"] if item["id"] == "GOLDEN-ARCH-001")
        contract = build_contract(case, contract_revision="eval-phase6")
        schema = yaml.safe_load((ROOT / "Eval" / "GoldenContracts" / "golden-contract.schema.yaml").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(contract)
        task = runtime_task_projection(case)
        self.assertEqual(task, case["task"])
        self.assertNotIn("expectation", task)
        self.assertTrue(contract["invariants"])
        self.assertTrue(contract["forbidden"])

    def test_change_proposal_never_applies_change(self):
        proposal = build_change_proposal(
            proposal_id="proposal-1", source_eval_refs=["eval-1"], target_authority="Runtime",
            proposed_change="Review timeout profile", rationale="Observed repeated infra timeout",
            evidence_refs=["evidence-1"], created_at="2026-08-29T05:00:00Z",
        )
        schema = yaml.safe_load((ROOT / "Eval" / "ChangeProposals" / "change-proposal.schema.yaml").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(proposal)
        self.assertFalse(proposal["applies_change"])
        self.assertTrue(proposal["requires_human_review"])

    def test_eval_record_v11_schema(self):
        record = build_eval_record(
            eval_id="eval-1", run_id="run-1", source_execution_result_ref="execution-result.json",
            failure_class=None, observation_state="observed", evidence_refs=["ev-1"],
        )
        schema = yaml.safe_load((ROOT / "Eval" / "Attribution" / "eval-record.schema.yaml").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(record)
        self.assertTrue(record["quality_denominator_eligible"])

    def test_historical_replay_requires_arch_naming_mutation_evidence_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = []
            for namespace in ("ARCH", "NAMING", "MUTATION", "EVIDENCE"):
                bundle = root / namespace.lower()
                bundle.mkdir()
                envelope = {
                    "schema_version": "1.0",
                    "run_id": f"run-{namespace.lower()}",
                    "golden_task_id": f"GOLDEN-{namespace}-001",
                    "status": "completed",
                    "executor": {"provider": "test", "model": "test", "model_revision": "1"},
                    "execution_fingerprint": {"unityagent_revision": "ua", "graph_engineering_revision": "graph"},
                    "evidence": {"metrics_ref": "metrics.json", "gate_evidence": []},
                }
                (bundle / "execution-envelope.yaml").write_text(yaml.safe_dump(envelope), encoding="utf-8")
                (bundle / "metrics.json").write_text(json.dumps({"changed_paths": []}), encoding="utf-8")
                inputs.append(bundle)
            report = replay(inputs, require_namespaces={"ARCH", "NAMING", "MUTATION", "EVIDENCE"})
            self.assertEqual(report["case_count"], 4)
            self.assertEqual(report["observed_namespaces"], ["ARCH", "EVIDENCE", "MUTATION", "NAMING"])

    def test_canonical_eval_control_modules_do_not_execute_runtime(self):
        paths = [
            ROOT / "Eval" / "Attribution" / "attribution.py",
            ROOT / "Eval" / "Behavior" / "runtime_adapter.py",
            ROOT / "Eval" / "Behavior" / "run_behavior_eval.py",
            ROOT / "Eval" / "GoldenContracts" / "build_contract.py",
            ROOT / "Eval" / "ChangeProposals" / "change_proposal.py",
            ROOT / "Eval" / "Replay" / "historical_replay.py",
        ]
        forbidden = ("subprocess", "process_runtime", "Runtime.Runner", "Runtime.Dispatcher")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{path}: {token}")


if __name__ == "__main__":
    unittest.main()
