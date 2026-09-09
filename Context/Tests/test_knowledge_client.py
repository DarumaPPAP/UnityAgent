from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Context.Retrieval.Knowledge.knowledge_client import (
    KnowledgeCitationState,
    KnowledgeClientOptions,
    KnowledgeContextAssembler,
    KnowledgeHttpClient,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)


def result_payload(chunk_id: str, document_id: str, source_units: list[str], content: str) -> dict:
    return {
        "rank": 1,
        "score": 0.9,
        "chunk_id": chunk_id,
        "document_id": document_id,
        "title": "Knowledge fixture",
        "content": content,
        "source_uri": "https://drive.google.com/file/d/drive-id/view",
        "drive_file_id": "drive-id",
        "source_revision": "sha256:source",
        "source_units": source_units,
        "citation": {"label": "Knowledge fixture page:1", "locator": "/".join(source_units)},
        "provenance": {"workspace_path": "sources/evidence/DOC-FIXTURE", "evidence_id": "EVD-1"},
    }


def response_payload(status: str = "success", results: list[dict] | None = None) -> dict:
    return {
        "status": status,
        "query_id": "qry-fixture",
        "index_revision": "idx-fixture",
        "results": results or [],
        "diagnostics": {
            "backend": "lexical",
            "latency_ms": 1,
            "candidate_count": len(results or []),
            "returned_count": len(results or []),
            "filtered_count": 0,
            "trace_id": "trace-fixture",
        },
    }


class KnowledgeClientTests(unittest.TestCase):
    def test_request_serialization_does_not_accept_identity_fields(self):
        request = KnowledgeSearchRequest(
            "RenderGraph",
            scope={"project": "UnityAgent", "domains": ["Rendering"]},
            filters={"topics": ["postprocess"]},
            top_k=4,
        )
        payload = request.to_payload()
        self.assertNotIn("identity", payload)
        self.assertNotIn("user_id", payload)
        self.assertEqual(payload["scope"]["project"], "UnityAgent")

    def test_response_requires_complete_provenance_and_preserves_status(self):
        response = KnowledgeSearchResponse.from_payload(
            response_payload("stale", [result_payload("CHK-1", "DOC-1", ["page:1"], "evidence")])
        )
        self.assertEqual(response.status, "stale")
        self.assertEqual(response.results[0].provenance.workspace_path, "sources/evidence/DOC-FIXTURE")
        state = KnowledgeCitationState()
        state.apply(response)
        self.assertEqual(state.status, "stale")
        self.assertEqual(state.index_revision, "idx-fixture")
        self.assertEqual(len(state.citations), 1)

        incomplete = result_payload("CHK-2", "DOC-2", ["page:1"], "evidence")
        del incomplete["provenance"]
        with self.assertRaisesRegex(ValueError, "incomplete provenance"):
            KnowledgeSearchResponse.from_payload(response_payload(results=[incomplete]))

    def test_context_assembler_keeps_distinct_source_units_and_trims_budget(self):
        first = result_payload("CHK-1", "DOC-1", ["page:1"], "12345")
        duplicate = result_payload("CHK-2", "DOC-1", ["page:1"], "duplicate")
        distinct = result_payload("CHK-3", "DOC-1", ["page:2"], "67890")
        distinct["rank"] = 2
        context = KnowledgeContextAssembler(max_characters=8).assemble(
            KnowledgeSearchResponse.from_payload(response_payload(results=[first, duplicate, distinct]))
        )
        self.assertEqual(context.consumed_characters, 8)
        self.assertEqual(len(context.items), 2)
        self.assertEqual(context.items[0].content, "12345")
        self.assertEqual(context.items[1].content, "678")
        self.assertEqual(context.trimmed_count, 2)

    def test_empty_and_blocked_results_are_not_added_to_context(self):
        for status in ("empty", "blocked", "unavailable"):
            response = KnowledgeSearchResponse.from_payload(response_payload(status))
            context = KnowledgeContextAssembler().assemble(response)
            self.assertEqual(context.status, status)
            self.assertEqual(context.items, ())

    def test_http_client_maps_transport_failure_and_opens_circuit(self):
        calls = []

        def failing_opener(*_args, **_kwargs):
            calls.append(True)
            raise urllib.error.URLError("offline")

        client = KnowledgeHttpClient(
            KnowledgeClientOptions(
                "http://127.0.0.1:1",
                bearer_token="secret-token",
                max_retries=0,
                circuit_failure_threshold=1,
                circuit_cooldown_seconds=60,
            ),
            opener=failing_opener,
        )
        first = client.search(KnowledgeSearchRequest("RenderGraph"))
        second = client.search(KnowledgeSearchRequest("RenderGraph"))
        self.assertEqual(first.status, "unavailable")
        self.assertEqual(second.status, "unavailable")
        self.assertEqual(len(calls), 1)

    def test_http_client_sends_bearer_and_parses_same_contract(self):
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(response_payload(results=[result_payload("CHK-1", "DOC-1", ["page:1"], "evidence")])).encode()

        def opener(request, **_kwargs):
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.data.decode())
            return Response()

        client = KnowledgeHttpClient(KnowledgeClientOptions("https://knowledge.example", bearer_token="secret-token"), opener=opener)
        response = client.search(KnowledgeSearchRequest("RenderGraph"))
        self.assertEqual(response.status, "success")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-token")
        self.assertNotIn("user_id", captured["body"])


if __name__ == "__main__":
    unittest.main()
