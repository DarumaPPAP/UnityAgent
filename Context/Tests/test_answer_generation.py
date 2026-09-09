from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Context.Retrieval.Knowledge.answer_generation import (
    AnswerRequest,
    DeterministicAnswerModel,
    KnowledgeAnswerGenerator,
)
from Context.Retrieval.Knowledge.knowledge_client import (
    KnowledgeSearchResponse,
)


def result_payload(index: int, content: str) -> dict:
    return {
        "rank": index + 1,
        "score": 0.9 - index / 10,
        "chunk_id": f"CHK-{index}",
        "document_id": "DOC-1",
        "title": "Rendering note",
        "content": content,
        "source_uri": "https://drive.google.com/file/d/drive-1/view",
        "drive_file_id": "drive-1",
        "source_revision": "source-1",
        "source_units": [f"page:{index + 1}"],
        "citation": {"label": f"Rendering note p.{index + 1}", "locator": f"page:{index + 1}"},
        "provenance": {"workspace_path": "runtime/knowledge/DOC-1", "evidence_id": f"EVD-{index}"},
    }


class FakeKnowledgeClient:
    def __init__(self, response):
        self.response = response

    def search(self, _request):
        return self.response


def response(status="success", results=None):
    return KnowledgeSearchResponse.from_payload(
        {
            "status": status,
            "query_id": "qry-1",
            "index_revision": "idx-hybrid-1",
            "results": results or [],
            "diagnostics": {
                "backend": "hybrid",
                "latency_ms": 1,
                "candidate_count": len(results or []),
                "returned_count": len(results or []),
                "filtered_count": 0,
                "trace_id": "trace-1",
            },
        }
    )


class AnswerGenerationTests(unittest.TestCase):
    def test_answer_has_citations_and_index_revision(self):
        generator = KnowledgeAnswerGenerator(
            FakeKnowledgeClient(response(results=[result_payload(0, "GPU visibility uses meshlet culling.")])) ,
            DeterministicAnswerModel(),
        )
        answer = generator.generate(AnswerRequest("How does visibility work?"))
        self.assertEqual(answer.status, "answered")
        self.assertEqual(answer.index_revision, "idx-hybrid-1")
        self.assertEqual(answer.coverage, 1.0)
        self.assertFalse(answer.abstained)
        self.assertEqual(len(answer.citations), 1)

    def test_empty_retrieval_abstains(self):
        generator = KnowledgeAnswerGenerator(FakeKnowledgeClient(response(status="empty")), DeterministicAnswerModel())
        answer = generator.generate(AnswerRequest("unknown"))
        self.assertEqual(answer.status, "retrieval_empty")
        self.assertIsNone(answer.answer)
        self.assertTrue(answer.abstained)

    def test_invalid_citation_coverage_does_not_return_success(self):
        class BadModel:
            model_version = "bad"

            def generate(self, **_kwargs):
                return {
                    "answer": "unsupported",
                    "claims": [{"text": "unsupported", "citation_indexes": [99]}],
                    "abstained": False,
                }

        generator = KnowledgeAnswerGenerator(
            FakeKnowledgeClient(response(results=[result_payload(0, "evidence")])),
            BadModel(),
        )
        answer = generator.generate(AnswerRequest("question"))
        self.assertEqual(answer.status, "insufficient_evidence")
        self.assertTrue(answer.abstained)

    def test_stale_retrieval_abstains_by_default(self):
        generator = KnowledgeAnswerGenerator(
            FakeKnowledgeClient(response(status="stale", results=[result_payload(0, "old evidence")])),
            DeterministicAnswerModel(),
        )
        answer = generator.generate(AnswerRequest("latest"))
        self.assertEqual(answer.status, "insufficient_evidence")
        self.assertTrue(answer.abstained)


if __name__ == "__main__":
    unittest.main()
