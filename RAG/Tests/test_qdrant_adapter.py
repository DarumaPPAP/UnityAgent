import unittest
from unittest.mock import patch

from RAG.Adapters.qdrant import (
    BM25SparseEncoder,
    HashingDenseEmbedder,
    QdrantCollectionManager,
    QdrantBackend,
    QdrantCollectionSchema,
    QdrantConfig,
    build_qdrant_filter,
    build_upsert_payload,
)
from RAG.Adapters.qdrant.transport import QdrantError
from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate, RetrievalFilters, RetrievalRequest
from RAG.Retrieval.local_lexical_backend import LocalLexicalBackend
from RAG.Retrieval.retrieval_service import retrieve_knowledge


class FakeQdrantTransport:
    def __init__(self, response=None, error=None):
        self.response = response or {"result": []}
        self.error = error
        self.calls = []

    def request(self, method, path, payload=None, *, timeout_seconds=10.0):
        self.calls.append((method, path, payload, timeout_seconds))
        if self.error:
            raise self.error
        return self.response


def candidate(candidate_id="candidate-1", text="RenderGraph Blit replacement"):
    return RetrievalCandidate(
        candidate_id=candidate_id,
        source_kind="my_resource_center",
        source_ref=f"mrc://evidence/{candidate_id}/EV-{candidate_id}",
        document_id=f"DOC-{candidate_id}",
        evidence_id=f"EV-{candidate_id}",
        heading="fixture",
        summary=text,
        content=text,
        metadata={
            "repository": "DarumaPPAP/MyResourceCenter",
            "domains": ["rendering"],
            "platforms": ["Switch"],
            "unity_versions": ["6000.x"],
            "render_pipelines": ["URP"],
        },
        provenance=CandidateProvenance(
            source_kind="my_resource_center",
            source_ref=f"mrc://evidence/{candidate_id}/EV-{candidate_id}",
            document_id=f"DOC-{candidate_id}",
            evidence_id=f"EV-{candidate_id}",
        ),
        confidence="verified",
        review_status="reviewed",
    )


class QdrantAdapterTests(unittest.TestCase):
    def setUp(self):
        self.config = QdrantConfig(
            url="https://qdrant.example.test:6333",
            collection="unityagent-knowledge",
            api_key="do-not-leak",
            dense_vector_size=8,
        )

    def request(self, **overrides):
        values = {
            "request_id": "req-qdrant",
            "raw_query": "Switch URP RenderGraph",
            "normalized_query": "switch urp rendergraph",
            "route_id": "graphics-mcp",
            "execution_profile": "generic_planning",
            "filters": RetrievalFilters.from_mapping({"platforms": ["Switch"], "render_pipeline": "URP"}),
            "top_k": 2,
            "candidate_k": 4,
            "max_chars": 256,
            "query_tokens": ("switch", "urp", "rendergraph"),
            "technical_tokens": ("rendergraph",),
        }
        values.update(overrides)
        return RetrievalRequest(**values)

    def test_query_uses_dense_sparse_prefetch_and_payload_filter(self):
        transport = FakeQdrantTransport()
        backend = QdrantBackend(self.config, transport=transport)
        payload = backend.build_query_payload(self.request())
        self.assertEqual(payload["query"], {"fusion": "rrf"})
        self.assertEqual(len(payload["prefetch"]), 2)
        self.assertEqual({item["using"] for item in payload["prefetch"]}, {"dense", "sparse"})
        filter_keys = {item["key"] for item in payload["prefetch"][0]["filter"]["must"]}
        self.assertEqual(filter_keys, {"platforms", "render_pipelines"})
        self.assertNotIn("do-not-leak", str(backend.capability_contract()))

    def test_qdrant_payload_maps_to_groundable_candidate(self):
        transport = FakeQdrantTransport({"result": [{
            "id": "point-1",
            "score": 0.8,
            "payload": {
                "candidate_id": "RAG-GFX-003",
                "document_id": "DOC-RAG-003",
                "evidence_id": "EV-RAG-003",
                "summary": "RenderGraph uses a raster pass instead of Blit.",
                "source_kind": "my_resource_center",
                "review_status": "reviewed",
                "confidence": "verified",
                "provenance": {
                    "source_kind": "my_resource_center",
                    "source_ref": "mrc://evidence/DOC-RAG-003/EV-RAG-003",
                    "document_id": "DOC-RAG-003",
                    "evidence_id": "EV-RAG-003",
                    "evidence_ids": ["EV-RAG-003"],
                    "source_units": [4],
                    "drive_file_id": "drive-rag-003",
                    "workspace_path": "sources/evidence/DOC-RAG-003",
                    "original_required": False,
                    "relation_refs": [],
                },
            },
        }]})
        backend = QdrantBackend(self.config, transport=transport)
        result = backend.retrieve(self.request())
        self.assertEqual(result[0].candidate_id, "RAG-GFX-003")
        self.assertEqual(result[0].fusion_score, 0.8)
        self.assertEqual(result[0].provenance.evidence_id, "EV-RAG-003")

    def test_unavailable_qdrant_requires_explicit_fallback(self):
        local_candidate = candidate()
        fallback = LocalLexicalBackend([local_candidate])
        backend = QdrantBackend(
            self.config,
            transport=FakeQdrantTransport(error=QdrantError("offline")),
            fallback=fallback,
            allow_fallback=True,
        )
        result = retrieve_knowledge(
            query="RenderGraph Blit replacement",
            route_id="graphics-mcp",
            execution_profile="generic_planning",
            backend=backend,
            top_k=1,
            candidate_k=2,
            max_chars=256,
        )
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["trace"]["fallback_used"])
        self.assertTrue(any(item["code"] == "backend_fallback" for item in result["diagnostics"]))

    def test_unavailable_qdrant_without_fallback_is_blocked(self):
        backend = QdrantBackend(
            self.config,
            transport=FakeQdrantTransport(error=QdrantError("offline")),
        )
        result = retrieve_knowledge(
            query="RenderGraph",
            route_id="graphics-mcp",
            execution_profile="generic_planning",
            backend=backend,
            top_k=1,
            candidate_k=2,
            max_chars=256,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["trace"]["fallback_used"])

    def test_collection_payload_supports_named_dense_and_sparse_vectors(self):
        item = candidate()
        payload = build_upsert_payload(
            [item],
            [[0.0] * 8],
            [BM25SparseEncoder().encode(item.summary)],
            schema=QdrantCollectionSchema(dense_dimension=8),
        )
        point = payload["points"][0]
        self.assertIn("dense", point["vector"])
        self.assertIn("sparse", point["vector"])
        self.assertEqual(point["payload"]["document_id"], "DOC-candidate-1")

    def test_filter_mapping_uses_qdrant_match_any_for_platforms(self):
        value = build_qdrant_filter(RetrievalFilters.from_mapping({"platforms": ["Switch", "PC"]}))
        self.assertEqual(value["must"][0]["match"], {"any": ["Switch", "PC"]})

    def test_collection_manager_indexes_before_upsert(self):
        transport = FakeQdrantTransport()
        manager = QdrantCollectionManager(self.config, transport=transport)
        result = manager.upsert_candidates(
            [candidate()],
            dense_embedder=HashingDenseEmbedder(8),
            sparse_encoder=BM25SparseEncoder(),
        )
        self.assertEqual(result["upserted"], 1)
        index_positions = [index for index, call in enumerate(transport.calls) if call[1].endswith("/index")]
        upsert_positions = [index for index, call in enumerate(transport.calls) if "/points?wait=true" in call[1]]
        self.assertTrue(index_positions)
        self.assertTrue(upsert_positions)
        self.assertLess(max(index_positions), min(upsert_positions))

    def test_environment_factory_is_optional_when_not_configured(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(QdrantBackend.from_environment())


if __name__ == "__main__":
    unittest.main()
