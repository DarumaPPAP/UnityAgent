from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Context.Retrieval.Knowledge.answer_generation import GroundedAnswer  # noqa: E402
from Context.Retrieval.Knowledge.knowledge_client import KnowledgeCitation  # noqa: E402
from Tools.run_knowledge_answer_acceptance import percentile, safe_base_url, validate_answer  # noqa: E402


class AnswerAcceptanceRunnerTests(unittest.TestCase):
    def test_safe_service_url_removes_userinfo_and_query(self):
        self.assertEqual(safe_base_url("https://user:secret@example.test:8443/api?token=bad"), "https://example.test:8443/api")

    def test_percentile_uses_nearest_rank(self):
        self.assertEqual(percentile([10, 20], 0.95), 20)

    def test_answer_validator_is_content_free_and_checks_grounding(self):
        answer = GroundedAnswer(
            status="answered",
            answer="hidden answer",
            citations=(KnowledgeCitation("safe citation", "page:1"),),
            claims=(),
            index_revision="idx-1",
            model_version="model-1",
            coverage=1.0,
            abstained=False,
            diagnostics={"retrieval_status": "success", "retrieval_trace_id": "trace-1"},
        )
        failures, safe = validate_answer(answer, {"id": "grounded", "expected_status": "answered", "minimum_citations": 0})
        self.assertEqual(failures, [])
        self.assertNotIn("answer", safe)
        self.assertEqual(safe["index_revision"], "idx-1")

    def test_answer_validator_rejects_unexpected_provider_success(self):
        answer = SimpleNamespace(
            status="answered",
            abstained=False,
            coverage=1.0,
            citations=[object()],
            index_revision="idx-1",
            model_version="model-1",
            diagnostics={},
        )
        failures, safe = validate_answer(answer, {"id": "failure", "expected_status": "generation_failed"})
        self.assertIn("unexpected_status:answered", failures)
        self.assertFalse(safe["passed"])


if __name__ == "__main__":
    unittest.main()
