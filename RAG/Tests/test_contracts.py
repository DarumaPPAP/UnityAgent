import unittest

from RAG.Contracts.models import CandidateProvenance, RetrievalRequest, RetrievalFilters
from RAG.Query.normalize_query import normalize_query


class RagContractTests(unittest.TestCase):
    def test_normalization_is_deterministic_and_keeps_identifier(self):
        first = normalize_query(" URP_COMPATIBILITY_MODE  ")
        second = normalize_query("URP_COMPATIBILITY_MODE")
        self.assertEqual(first.query_hash, second.query_hash)
        self.assertIn("urp_compatibility_mode", first.technical_tokens)

    def test_request_rejects_unbounded_limits(self):
        with self.assertRaises(ValueError):
            RetrievalRequest(
                request_id="req-1",
                raw_query="shader",
                normalized_query="shader",
                route_id="graphics-mcp",
                execution_profile="generic_planning",
                top_k=21,
            )

    def test_provenance_requires_uri_but_allows_evidence_or_document_identity(self):
        provenance = CandidateProvenance(
            source_kind="my_resource_center",
            source_ref="mrc://evidence/DOC-1/EV-1",
            evidence_id="EV-1",
        )
        self.assertTrue(provenance.has_identity)
        self.assertEqual(RetrievalFilters.from_mapping({"platform": "Switch"}).platforms, ("Switch",))


if __name__ == "__main__":
    unittest.main()
