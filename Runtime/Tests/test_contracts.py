import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]


def load_all():
    paths = list(ROOT.glob("**/Contracts/*.schema.yaml"))
    schemas = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]
    return {schema["$id"]: schema for schema in schemas}


class RuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = load_all()

    def validate(self, schema_id, value):
        schema = self.store[schema_id]
        Draft202012Validator(schema, resolver=RefResolver.from_schema(schema, store=self.store)).validate(value)

    def fp(self):
        return {
            "schema_version": "1.0", "architecture_version": "test", "policy_revision": "p",
            "prompt_revision": "q", "context_revision": "c", "graph_revision": "g",
            "runtime_profile_revision": "r", "tool_schema_revision": "t",
            "checkpoint_schema_revision": "cp", "evidence_schema_revision": "e",
            "eval_contract_revision": "v",
        }

    def test_execution_result_preserves_not_observed_changed_paths(self):
        value = {
            "schema_version": "1.0", "run_id": "run", "step_id": "step", "action_id": "action",
            "status": "passed", "started_at": None, "completed_at": None, "exit_code": 0,
            "runtime_failure": None,
            "changed_paths": {"observation_state": "not_observed", "paths": []},
            "gate_outcomes": [],
            "tool_identity": {"provider": "fixture", "model": "fixture", "model_revision": "1", "tool_manifest_hash": "hash", "executor_profile": None, "execution_mode": None},
            "evidence_refs": [], "telemetry_refs": [], "definition_fingerprint": self.fp(),
        }
        self.validate("urn:unityagent:runtime:execution-result", value)

    def test_mutation_scope_requires_not_observed_when_paths_not_observed(self):
        value = {
            "schema_version": "1.0", "mutation_id": "m", "run_id": "r", "step_id": "s",
            "scope": {"allowed_paths": [], "prohibited_paths": []},
            "changed_paths": {"observation_state": "not_observed", "paths": []},
            "diff_ref": None, "before_fingerprint": None, "after_fingerprint": None,
            "scope_status": "within_scope", "verification_refs": [],
        }
        with self.assertRaises(Exception):
            self.validate("urn:unityagent:runtime:mutation-evidence", value)


if __name__ == "__main__":
    unittest.main()
