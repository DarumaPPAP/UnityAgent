import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


class OperationsContractTests(unittest.TestCase):
    def test_trace_record_is_structured_and_evidence_linked(self):
        schema = yaml.safe_load((ROOT / "Operations/Observability/trace-record.schema.yaml").read_text(encoding="utf-8"))
        value = {
            "schema_version": "1.0", "trace_id": "trace", "span_id": "span", "parent_span_id": None,
            "run_id": "run", "step_id": "step", "event_type": "tool.completed", "severity": "info",
            "timestamp": "2026-08-29T00:00:00Z", "attributes": {"duration_ms": 10}, "evidence_refs": ["evidence:1"],
        }
        Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
