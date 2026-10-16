"""Read-only approval review Skill must never imply executable approval authority."""
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents/skills/approval-optimization-review/SKILL.md"
PROPOSAL = ROOT / "eval/change_proposals/change_proposal.py"


class ApprovalOptimizationReviewTests(unittest.TestCase):
    def test_skill_declares_read_only_capabilities(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("name: approval-optimization-review", text)
        self.assertIn("allowed-tools:\n  - Read\n", text)
        self.assertIn("ファイルを変更しない", text)
        self.assertIn("Approval Decision", text)
        self.assertIn("requires_human_review: true", text)
        self.assertIn("applies_change: false", text)
        self.assertIn("Source Revision", text)
        self.assertIn("Scope", text)
        self.assertIn("Rollback", text)

    def test_existing_proposal_builder_is_non_applying(self):
        build = runpy.run_path(str(PROPOSAL))["build_change_proposal"]
        result = build(
            proposal_id="approval-review-fixture",
            source_eval_refs=["eval/run-example"],
            target_authority="Policy",
            proposed_change="Consider an approval request notification only after regression.",
            rationale="Measured waiting time would support an explicit human review.",
            evidence_refs=["evidence/run-example"],
            created_at="2026-10-16T00:00:00+00:00",
        )
        self.assertEqual(result["status"], "proposed")
        self.assertFalse(result["applies_change"])
        self.assertTrue(result["requires_human_review"])
        self.assertEqual(result["evidence_refs"], ["evidence/run-example"])


if __name__ == "__main__":
    unittest.main()
