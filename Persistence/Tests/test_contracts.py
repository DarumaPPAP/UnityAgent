import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = {}
for path in ROOT.glob("**/Contracts/*.schema.yaml"):
    schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    SCHEMAS[schema["$id"]] = schema


class PersistenceContractTests(unittest.TestCase):
    def validate(self, schema_id, value):
        schema = SCHEMAS[schema_id]
        Draft202012Validator(schema, resolver=RefResolver.from_schema(schema, store=SCHEMAS)).validate(value)

    def test_loop_control_has_semantic_state_not_runtime_retry_controls(self):
        schema = SCHEMAS["urn:unityagent:persistence:loop-control-state"]
        props = set(schema["properties"])
        self.assertFalse({"timeout_seconds", "hard_retry_ceiling", "cost_ceiling", "max_turns"} & props)

    def test_memory_requires_source_evidence(self):
        value = {
            "schema_version": "1.0", "memory_id": "m", "statement": "verified fact",
            "scope_class": "project_internal", "confidence": "verified", "source_evidence_refs": [],
            "created_at": "2026-08-29T00:00:00Z", "updated_at": "2026-08-29T00:00:00Z",
        }
        with self.assertRaises(Exception):
            self.validate("urn:unityagent:persistence:memory-record", value)


if __name__ == "__main__":
    unittest.main()
