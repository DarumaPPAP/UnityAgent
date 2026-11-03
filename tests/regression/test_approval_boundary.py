"""ApprovalDecisionStoreの取消、Plan束縛、単回消費を実FSで検証する。"""
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.store.atomic_store import PersistenceError


class ApprovalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="unityagent-approval-")
        self.addCleanup(self.temporary.cleanup)
        self.store = ApprovalDecisionStore(self.temporary.name)

    def test_revocation_survives_reregistration(self):
        decision = {
            "approval_decision_id": "approval-A",
            "decision_digest": "sha256:reviewed-A",
            "revocation_epoch": 0,
        }
        self.store.register(decision)
        self.assertEqual(self.store.revoke("approval-A"), 1)
        self.store.register(decision)

        self.assertEqual(self.store.get("approval-A")["current_revocation_epoch"], 1)

    def test_other_plan_digest_cannot_be_bound(self):
        self.store.register({
            "approval_decision_id": "approval-A",
            "decision_digest": "sha256:reviewed-A",
            "revocation_epoch": 0,
        })
        with self.assertRaises(PersistenceError) as captured:
            self.store.bind_artist_plan("approval-A", {
                "approvalDigest": "sha256:another-decision",
                "planId": "plan-B",
            })

        self.assertEqual(captured.exception.code, "approval_binding_mismatch")
        self.assertNotIn("artist_plan", self.store.get("approval-A"))

    def test_reviewed_plan_cannot_be_replaced(self):
        self.store.register({
            "approval_decision_id": "approval-A",
            "decision_digest": "sha256:reviewed-A",
            "revocation_epoch": 0,
        })
        original = {"approvalDigest": "sha256:reviewed-A", "planId": "plan-A"}
        self.store.bind_artist_plan("approval-A", original)

        with self.assertRaises(PersistenceError) as captured:
            self.store.bind_artist_plan("approval-A", {
                "approvalDigest": "sha256:reviewed-A",
                "planId": "plan-B",
            })

        self.assertEqual(captured.exception.code, "immutable_record_conflict")
        self.assertEqual(self.store.get("approval-A")["artist_plan"], original)

    def test_failed_validation_never_consumes_approval(self):
        self.store.register({
            "approval_decision_id": "approval-A",
            "decision_digest": "sha256:reviewed-A",
            "revocation_epoch": 0,
        })
        binding = {"approvalDigest": "sha256:reviewed-A", "planId": "plan-A"}
        self.store.bind_artist_plan("approval-A", binding)

        def reject():
            raise PersistenceError("approval_revoked", "the approval is revoked")

        with self.assertRaises(PersistenceError) as captured:
            self.store.consume_artist_plan(
                "approval-A", binding, validate=reject, reservation_id="reservation-A"
            )

        self.assertEqual(captured.exception.code, "approval_revoked")
        self.assertNotIn("artist_consumption", self.store.get("approval-A"))

    def test_wrong_binding_never_reaches_validation(self):
        self.store.register({
            "approval_decision_id": "approval-A",
            "decision_digest": "sha256:reviewed-A",
            "revocation_epoch": 0,
        })
        binding = {"approvalDigest": "sha256:reviewed-A", "planId": "plan-A"}
        self.store.bind_artist_plan("approval-A", binding)
        verifier = Mock()

        with self.assertRaises(PersistenceError) as captured:
            self.store.consume_artist_plan(
                "approval-A",
                {"approvalDigest": "sha256:reviewed-A", "planId": "plan-B"},
                validate=verifier,
                reservation_id="reservation-B",
            )

        self.assertEqual(captured.exception.code, "approval_binding_mismatch")
        verifier.assert_not_called()
        self.assertNotIn("artist_consumption", self.store.get("approval-A"))

    def test_successful_consumption_is_durable_and_single_use(self):
        self.store.register({
            "approval_decision_id": "approval-A",
            "decision_digest": "sha256:reviewed-A",
            "revocation_epoch": 0,
        })
        binding = {"approvalDigest": "sha256:reviewed-A", "planId": "plan-A"}
        self.store.bind_artist_plan("approval-A", binding)
        verifier = Mock()

        self.store.consume_artist_plan(
            "approval-A", binding, validate=verifier, reservation_id="reservation-A"
        )
        verifier.assert_called_once_with()
        self.assertEqual(
            ApprovalDecisionStore(self.temporary.name).get("approval-A")["artist_consumption"],
            {"reservation_id": "reservation-A", "binding": binding, "state": "execution_started"},
        )
        verifier.reset_mock()

        with self.assertRaises(PersistenceError) as captured:
            self.store.consume_artist_plan(
                "approval-A", binding, validate=verifier, reservation_id="reservation-B"
            )

        self.assertEqual(captured.exception.code, "approval_already_used")
        verifier.assert_not_called()
        self.assertEqual(
            self.store.get("approval-A")["artist_consumption"]["reservation_id"],
            "reservation-A",
        )

    def test_reregistration_does_not_clear_consumption(self):
        decision = {
            "approval_decision_id": "approval-A",
            "decision_digest": "sha256:reviewed-A",
            "revocation_epoch": 0,
        }
        binding = {"approvalDigest": "sha256:reviewed-A", "planId": "plan-A"}
        self.store.register(decision)
        self.store.bind_artist_plan("approval-A", binding)
        self.store.consume_artist_plan(
            "approval-A", binding, validate=lambda: None, reservation_id="reservation-A"
        )
        self.store.register(decision)

        self.assertEqual(
            self.store.get("approval-A")["artist_consumption"]["state"],
            "execution_started",
        )


if __name__ == "__main__":
    unittest.main()
