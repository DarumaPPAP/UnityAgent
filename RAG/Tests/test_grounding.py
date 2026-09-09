import unittest

from RAG.Contracts.models import CandidateProvenance, RetrievalCandidate, RetrievalRequest
from RAG.Grounding.context_projector import project_grounding_bundle
from RAG.Grounding.grounding_builder import build_grounding_bundle


class GroundingTests(unittest.TestCase):
    def request(self) -> RetrievalRequest:
        return RetrievalRequest(
            request_id="req-grounding",
            raw_query="shader",
            normalized_query="shader",
            route_id="graphics-mcp",
            execution_profile="generic_planning",
            max_chars=256,
        )

    def test_provenance_stays_with_bounded_statement(self):
        candidate = RetrievalCandidate(
            candidate_id="candidate-1",
            source_kind="fixture",
            source_ref="fixture://candidate-1",
            document_id="DOC-1",
            evidence_id="EV-1",
            heading="heading",
            summary="x" * 500,
            content="x" * 500,
            metadata={},
            provenance=CandidateProvenance(
                source_kind="fixture",
                source_ref="fixture://candidate-1",
                document_id="DOC-1",
                evidence_id="EV-1",
            ),
        )
        bundle = build_grounding_bundle(self.request(), [candidate], max_chars=256)
        self.assertEqual(bundle.status, "grounded")
        self.assertTrue(bundle.items[0]["provenance"]["evidence_id"])
        self.assertLessEqual(len(bundle.items[0]["statement"]), 256)
        projection = project_grounding_bundle(bundle)
        self.assertEqual(projection["grounding_bundle_ref"], bundle.reference)

    def test_missing_provenance_is_blocked_or_skipped(self):
        candidate = RetrievalCandidate(
            candidate_id="candidate-2",
            source_kind="fixture",
            source_ref="fixture://candidate-2",
            document_id=None,
            evidence_id=None,
            heading="heading",
            summary="unidentified",
            content="unidentified",
            metadata={},
            provenance=CandidateProvenance(source_kind="fixture", source_ref="fixture://candidate-2"),
        )
        bundle = build_grounding_bundle(self.request(), [candidate])
        self.assertEqual(bundle.status, "no_answer")
        self.assertEqual(len(bundle.items), 0)


if __name__ == "__main__":
    unittest.main()
