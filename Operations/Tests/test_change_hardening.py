import unittest

from Operations.ChangeManagement.change_manager import ChangeManagementError, authorize_change, build_change_request


class Phase7ChangeHardeningTests(unittest.TestCase):
    def _rollback(self) -> dict:
        return build_change_request(
            change_id="rollback-7",
            kind="rollback",
            current_manifest_id="manifest-current",
            target_manifest_id="manifest-previous",
            summary="rollback after incident",
            created_at="2026-08-29T06:20:00Z",
        )

    def test_generic_rollback_rejects_missing_or_downgraded_risk(self):
        request = self._rollback()
        for decision in (
            {"allowed": True, "approval_required": True, "decision_ref": "policy-1"},
            {"allowed": True, "risk_level": "R3", "approval_required": True, "decision_ref": "policy-2"},
            {"allowed": True, "risk_level": "R4", "approval_required": False, "decision_ref": "policy-3"},
        ):
            with self.assertRaises(ChangeManagementError):
                authorize_change(
                    request,
                    policy_decision=decision,
                    approval_decision={"status": "approved", "decision_ref": "approval-7"},
                )

    def test_generic_rollback_requires_explicit_approval(self):
        request = self._rollback()
        with self.assertRaises(ChangeManagementError):
            authorize_change(
                request,
                policy_decision={
                    "allowed": True,
                    "risk_level": "R4",
                    "approval_required": True,
                    "decision_ref": "policy-r4",
                },
                approval_decision={"status": "not_required", "decision_ref": "approval-none"},
            )

    def test_generic_rollback_accepts_only_r4_approved_path(self):
        request = self._rollback()
        authorized = authorize_change(
            request,
            policy_decision={
                "allowed": True,
                "risk_level": "R4",
                "approval_required": True,
                "decision_ref": "policy-r4",
            },
            approval_decision={"status": "approved", "decision_ref": "approval-r4"},
        )
        self.assertEqual(authorized["status"], "authorized")
        self.assertEqual(authorized["policy_decision_ref"], "policy-r4")
        self.assertEqual(authorized["approval_decision_ref"], "approval-r4")


if __name__ == "__main__":
    unittest.main()
