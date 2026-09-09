import unittest

from RAG.Feedback.experience_feedback import build_promotion_proposal


class FeedbackProposalTests(unittest.TestCase):
    def test_passed_eval_creates_stable_evidence_bound_proposal(self):
        evaluation = {
            "run_id": "eval-rag-1",
            "decision": "PASS",
            "generated_at": "2026-09-09T00:00:00+00:00",
            "metrics": {"recall_at_5": 1.0},
        }
        first = build_promotion_proposal(
            evaluation,
            evaluation_case_id="RAG-GOLDEN-003",
            query="RenderGraph Blit replacement",
            statement="RenderGraph uses a raster pass and explicit texture access instead of legacy Blit.",
            source_evidence_refs=["EV-RAG-003"],
            source_revision="sha256:index-v1",
            applicability=["rendering", "URP"],
        )
        second = build_promotion_proposal(
            evaluation,
            evaluation_case_id="RAG-GOLDEN-003",
            query="RenderGraph Blit replacement",
            statement="RenderGraph uses a raster pass and explicit texture access instead of legacy Blit.",
            source_evidence_refs=["EV-RAG-003"],
            source_revision="sha256:index-v1",
            applicability=["rendering", "URP"],
        )
        self.assertEqual(first, second)
        self.assertEqual(first["kind"], "rag_promotion_proposal")
        self.assertEqual(first["evaluation_decision"], "PASS")
        self.assertEqual(first["source_evidence_refs"], ["EV-RAG-003"])
        self.assertTrue(first["query_fingerprint"].startswith("sha256:"))

    def test_failed_eval_cannot_create_a_promotion_proposal(self):
        with self.assertRaises(ValueError):
            build_promotion_proposal(
                {"run_id": "eval-rag-fail", "decision": "FAIL"},
                query="unsafe guess",
                statement="This must not be promoted",
                source_evidence_refs=["EV-FAIL"],
                source_revision="sha256:index-v1",
            )


if __name__ == "__main__":
    unittest.main()
