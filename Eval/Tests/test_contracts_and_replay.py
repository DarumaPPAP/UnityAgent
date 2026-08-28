import json
import tempfile
import unittest
from pathlib import Path
import sys
import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Eval" / "Replay"))
from legacy_bundle_normalizer import NormalizationError, normalize_bundle

SCHEMAS = {}
for path in list(ROOT.glob("**/Contracts/*.schema.yaml")) + list(ROOT.glob("Operations/Observability/*.schema.yaml")) + list(ROOT.glob("Eval/Attribution/*.schema.yaml")) + list(ROOT.glob("Eval/GoldenContracts/*.schema.yaml")):
    schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    SCHEMAS[schema["$id"]] = schema


def validate(schema_id, value):
    schema = SCHEMAS[schema_id]
    Draft202012Validator(schema, resolver=RefResolver.from_schema(schema, store=SCHEMAS)).validate(value)


class EvalContractTests(unittest.TestCase):
    def test_infrastructure_failure_never_enters_agent_quality_denominator(self):
        value = {
            "schema_version": "1.0", "eval_id": "eval", "run_id": "run", "observation_state": "not_observed",
            "failure_class": "runtime_timeout", "quality_denominator_eligible": False,
            "runtime_failure_ref": "failure:1", "evidence_refs": [], "reason": "timeout",
            "source_execution_result_ref": "result:1",
        }
        validate("urn:unityagent:eval:eval-record", value)
        broken = dict(value)
        broken["quality_denominator_eligible"] = True
        with self.assertRaises(Exception):
            validate("urn:unityagent:eval:eval-record", broken)

    def test_existing_legacy_protocol_fixture_normalizes_without_inventing_changed_paths(self):
        bundle = ROOT / "Tests" / "BehaviorEval" / "ProtocolFixtures" / "valid"
        result = normalize_bundle(bundle)
        execution = result["execution_result"]
        self.assertEqual(execution["changed_paths"], {"observation_state": "not_observed", "paths": []})
        validate("urn:unityagent:runtime:execution-result", execution)
        validate("urn:unityagent:eval:eval-record", result["eval_record"])

    def test_structured_metrics_changed_paths_are_preserved_without_diff_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            envelope = {
                "schema_version": "1.1", "run_id": "legacy-run", "golden_task_id": "GOLDEN-MUTATION",
                "executor": {"provider": "codex", "model": "fixture", "model_revision": "1", "profile": "production", "mode": "prompt"},
                "status": "failed",
                "failure": {"class": "agent_behavior_regression", "reason": "mutation no-op contract", "observation_state": "observed"},
                "evidence": {"gate_evidence": [], "metrics_ref": "metrics.json", "diff": "diff.patch", "artifact_index": "artifact-index.yaml"},
                "execution_fingerprint": {"unityagent_revision": "u", "graph_engineering_revision": "g", "golden_suite_revision": "gold", "execution_profile": "production", "execution_mode": "prompt", "tool_manifest_hash": "tool"},
            }
            (bundle / "execution-envelope.yaml").write_text(yaml.safe_dump(envelope, sort_keys=False), encoding="utf-8")
            (bundle / "metrics.json").write_text(json.dumps({"changed_paths": ["Assets/A.cs"]}), encoding="utf-8")
            (bundle / "diff.patch").write_text("intentionally unrelated text", encoding="utf-8")
            result = normalize_bundle(bundle)
            self.assertEqual(result["execution_result"]["changed_paths"], {"observation_state": "observed", "paths": ["Assets/A.cs"]})

    def test_invalid_metrics_changed_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            envelope = {
                "schema_version": "1.1", "run_id": "legacy-run", "executor": {}, "status": "completed",
                "evidence": {"gate_evidence": [], "metrics_ref": "metrics.json"}, "execution_fingerprint": {},
            }
            (bundle / "execution-envelope.yaml").write_text(yaml.safe_dump(envelope), encoding="utf-8")
            (bundle / "metrics.json").write_text(json.dumps({"changed_paths": "Assets/A.cs"}), encoding="utf-8")
            with self.assertRaises(NormalizationError):
                normalize_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
