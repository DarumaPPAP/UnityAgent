import unittest

from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate, RetrievalRequest, RetrievalFilters
from RAG.Retrieval.local_lexical_backend import LocalLexicalBackend


def candidate(candidate_id: str, text: str, *, platform: str = "PC") -> RetrievalCandidate:
    return RetrievalCandidate(
        candidate_id=candidate_id,
        source_kind="fixture",
        source_ref=f"fixture://{candidate_id}",
        document_id=candidate_id,
        evidence_id=f"EV-{candidate_id}",
        heading="fixture",
        summary=text,
        content=text,
        metadata={"platforms": [platform], "domains": ["rendering"]},
        provenance=CandidateProvenance(
            source_kind="fixture",
            source_ref=f"fixture://{candidate_id}",
            document_id=candidate_id,
            evidence_id=f"EV-{candidate_id}",
        ),
        confidence="reviewed",
        review_status="reviewed",
    )


class LexicalRetrievalTests(unittest.TestCase):
    def request(self, query: str, filters: RetrievalFilters | None = None) -> RetrievalRequest:
        return RetrievalRequest(
            request_id="req-test",
            raw_query=query,
            normalized_query=query.casefold(),
            route_id="test",
            execution_profile="generic_planning",
            filters=filters or RetrievalFilters(),
        )

    def test_exact_identifier_ranks_above_review_bonus_only_records(self):
        backend = LocalLexicalBackend([candidate("exact", "RenderMeshIndirect indexed args"), candidate("other", "reviewed rendering note")])
        result = backend.retrieve(self.request("RenderMeshIndirect indexed"))
        self.assertEqual(result[0].candidate_id, "exact")

    def test_no_query_overlap_is_not_an_answer(self):
        backend = LocalLexicalBackend([candidate("one", "rendering note")])
        self.assertEqual(backend.retrieve(self.request("UnknownApi")), [])

    def test_platform_is_a_hard_filter(self):
        backend = LocalLexicalBackend([candidate("pc", "shader variants", platform="PC"), candidate("switch", "shader variants", platform="Switch")])
        result = backend.retrieve(self.request("shader variants", RetrievalFilters(platforms=("Switch",))))
        self.assertEqual([item.candidate_id for item in result], ["switch"])


if __name__ == "__main__":
    unittest.main()
