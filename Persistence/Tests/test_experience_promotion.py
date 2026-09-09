import tempfile
import unittest
from pathlib import Path

from Persistence.Memory.memory_store import MemoryStore
from Persistence.Memory.promotion_writer import persist_promotion_proposal


def proposal(
    proposal_id: str,
    *,
    source_revision: str = "sha256:index-v1",
    review_status: str = "pending",
    promotion_target: str = "execution_reference",
):
    return {
        "schema_version": "1.0",
        "kind": "rag_promotion_proposal",
        "proposal_id": proposal_id,
        "feedback_id": f"feedback-{proposal_id}",
        "evaluation_run_id": "eval-rag-1",
        "evaluation_case_id": "RAG-GOLDEN-003",
        "evaluation_decision": "PASS",
        "verification_status": "passed",
        "query": "RenderGraph Blit replacement",
        "query_fingerprint": "sha256:rendergraph-blit",
        "statement": "RenderGraph uses a raster pass and explicit texture access.",
        "source_evidence_refs": ["EV-RAG-003"],
        "source_memory_refs": [],
        "source_revision": source_revision,
        "applicability": ["rendering", "URP"],
        "limits": ["Verify the target Unity version."],
        "scope_class": "portable_artifact",
        "promotion_target": promotion_target,
        "review_status": review_status,
        "supersedes": [],
        "conflicts_with": [],
        "evaluation_metrics": {"recall_at_5": 1.0},
        "created_at": "2026-09-09T00:00:00+00:00",
        "definition_fingerprint": None,
    }


class ExperiencePromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = MemoryStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_pending_proposal_is_personal_only_and_gate_is_blocked(self):
        result = persist_promotion_proposal(self.store, proposal("proposal-pending"))
        self.assertTrue(result["persisted"])
        self.assertEqual(result["memory_record"]["scope_class"], "project_internal")
        self.assertEqual(result["memory_record"]["confidence"], "probable")
        self.assertEqual(self.store.list_accessible("generic_planning"), [])
        self.assertFalse(result["promotion_decision"]["approved"])
        self.assertFalse(result["promotion_decision"]["writes_external_authority"])

    def test_approved_proposal_is_idempotent_and_readable_by_rag_adapter(self):
        approved = proposal("proposal-approved", review_status="approved")
        first = persist_promotion_proposal(self.store, approved)
        second = persist_promotion_proposal(self.store, approved)
        self.assertTrue(first["persisted"])
        self.assertFalse(second["persisted"])
        self.assertEqual(first["memory_record"]["scope_class"], "portable_artifact")
        self.assertEqual(first["memory_record"]["confidence"], "verified")
        self.assertTrue(first["promotion_decision"]["approved"])
        self.assertEqual(len(self.store.list_accessible("generic_planning")), 1)
        # The next retrieval sees only the read-only projection and its revision.
        from RAG.Adapters.memory.adapter import MemoryAdapter
        loaded = MemoryAdapter(self.root, "generic_planning").load()
        self.assertEqual(loaded.candidates[0].metadata["source_revision"], "sha256:index-v1")

    def test_new_source_revision_is_recorded_as_a_conflict(self):
        persist_promotion_proposal(self.store, proposal("proposal-old", review_status="approved"))
        result = persist_promotion_proposal(
            self.store,
            proposal("proposal-new", source_revision="sha256:index-v2", review_status="approved"),
        )
        self.assertEqual(result["memory_record"]["conflicts_with"], ["proposal-old"])
        self.assertEqual(result["memory_record"]["source_revision"], "sha256:index-v2")

    def test_user_policy_target_still_requires_human_gate(self):
        candidate = proposal(
            "proposal-policy",
            review_status="approved",
            promotion_target="user_policy_candidate",
        )
        blocked = persist_promotion_proposal(self.store, candidate, human_gate_approved=False)
        self.assertFalse(blocked["promotion_decision"]["approved"])
        approved = persist_promotion_proposal(self.store, candidate, human_gate_approved=True)
        self.assertTrue(approved["promotion_decision"]["approved"])

    def test_rejected_or_unverified_proposals_are_not_written(self):
        with self.assertRaises(Exception) as rejected:
            persist_promotion_proposal(self.store, proposal("proposal-rejected", review_status="rejected"))
        self.assertEqual(rejected.exception.code, "promotion_rejected")
        unverified = proposal("proposal-unverified", review_status="approved")
        unverified["verification_status"] = "unverified"
        with self.assertRaises(Exception) as verification:
            persist_promotion_proposal(self.store, unverified)
        self.assertEqual(verification.exception.code, "promotion_requires_verified")


if __name__ == "__main__":
    unittest.main()
