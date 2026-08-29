from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_builder():
    path = ROOT / "Context/Manifest/build_context_manifest.py"
    spec = importlib.util.spec_from_file_location("phase8_context_manifest_builder", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fact(*, observed: int, checked: int, status: str = "current") -> dict:
    return {
        "key": "unity_version",
        "value": "6000.3.12f1",
        "source_kind": "detected_project",
        "source_path": "ProjectSettings/ProjectVersion.txt",
        "revision": "sha256:test",
        "observed_at_attempt": observed,
        "freshness": {"status": status, "checked_at_attempt": checked},
        "reason": "detected from target project",
    }


class ProjectFactFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()

    def test_retry_rejects_previous_current_fact_without_current_attempt_revalidation(self):
        with self.assertRaisesRegex(ValueError, "reobserved or revalidated"):
            self.builder.validate_project_facts([fact(observed=1, checked=1)], attempt=2)

    def test_retry_accepts_same_revision_after_current_attempt_revalidation(self):
        self.builder.validate_project_facts([fact(observed=1, checked=2)], attempt=2)

    def test_observation_cannot_come_from_future_attempt(self):
        with self.assertRaisesRegex(ValueError, "current manifest history"):
            self.builder.validate_project_facts([fact(observed=3, checked=3)], attempt=2)

    def test_checked_attempt_cannot_precede_observation(self):
        with self.assertRaisesRegex(ValueError, "between observation and current attempt"):
            self.builder.validate_project_facts([fact(observed=2, checked=1, status="stale")], attempt=2)

    def test_retry_manifest_requires_previous_manifest_reference(self):
        with self.assertRaisesRegex(ValueError, "previous_manifest_ref"):
            self.builder.build("phase8-freshness", "csharp-local-fix", attempt=2)


if __name__ == "__main__":
    unittest.main()
