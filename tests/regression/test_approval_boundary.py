"""ApprovalDecisionStoreの取消、Plan束縛、単回消費を実FSで検証する。"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.store.atomic_store import PersistenceError, read_json, sha256_json
from unityagent.persistence.state.state_store import StateStore
from unityagent.control_plane.csharp_fix import before_capability
from unityagent.runtime.guardrails.csharp_patch import project_revision


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


class ApprovalDispatchTests(unittest.TestCase):
    """本番の限定C#実行前Gateを実Project Revisionと実承認Storeで通す。"""

    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="unityagent-approval-dispatch-")
        self.addCleanup(self.temporary.cleanup)
        workspace = Path(self.temporary.name)
        self.project = workspace / "project"
        self.state_root = workspace / "state"
        for name in ("Assets", "Packages", "ProjectSettings"):
            (self.project / name).mkdir(parents=True)
        self.source = self.project / "Assets" / "Sample.cs"
        self.source.write_text(
            "public class Sample { public int Get() { return 1; } }\n",
            encoding="utf-8",
        )
        self.plane = SimpleNamespace(state_store=StateStore(self.state_root))
        self.store = ApprovalDecisionStore(self.state_root)
        self.revision = project_revision(self.project)
        self.plan = {
            "plan_id": "plan-A",
            "project_root": str(self.project),
            "expected_revision": self.revision,
            "intent": {"target_source": "Assets/Sample.cs"},
        }

    def register_decision(self, *, scope_paths, expires_at):
        decision = {
            "schema_version": "1.0",
            "approval_decision_id": "csharp-A",
            "operation": "csharp_local_fix",
            "plan_id": "plan-A",
            "plan_digest": sha256_json(self.plan),
            "project_root": str(self.project),
            "expected_revision": self.revision,
            "scope_paths": scope_paths,
            "human_review": "approved",
            "status": "active",
            "approved_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "expires_at": expires_at,
            "revocation_epoch": 0,
        }
        decision["decision_digest"] = sha256_json(decision)
        self.store.register(decision)

    def dispatch(self):
        session = {
            "plan": self.plan,
            "project": str(self.project),
            "intent": {"expected_revision": self.revision},
            "entry": {"approval_ref": "csharp-A"},
        }
        before_capability(self.plane, session, "source.patch", "run-A")
        return session

    def application_path(self):
        return self.state_root / "csharp-fixes" / "applications" / "plan-A.json"

    def test_reviewed_plan_records_dispatch_boundary_without_mutating_source(self):
        self.register_decision(
            scope_paths=["Assets/Sample.cs"],
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        )
        original = self.source.read_bytes()

        session = self.dispatch()

        self.assertEqual(session["input_revision"], self.revision)
        self.assertEqual(
            read_json(self.application_path()),
            {"plan_id": "plan-A", "run_id": "run-A", "phase": "dispatching", "evidence_refs": []},
        )
        self.assertEqual(self.source.read_bytes(), original)

    def test_revoked_approval_cannot_reach_dispatch_marker(self):
        self.register_decision(
            scope_paths=["Assets/Sample.cs"],
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        )
        self.store.revoke("csharp-A")
        original = self.source.read_bytes()

        with self.assertRaisesRegex(ValueError, "approval is missing, stale, revoked"):
            self.dispatch()

        self.assertFalse(self.application_path().exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_wrong_scope_cannot_reach_dispatch_marker(self):
        self.register_decision(
            scope_paths=["Assets/Other.cs"],
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        )
        original = self.source.read_bytes()

        with self.assertRaisesRegex(ValueError, "approval is missing, stale, revoked"):
            self.dispatch()

        self.assertFalse(self.application_path().exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_expired_approval_cannot_reach_dispatch_marker(self):
        self.register_decision(
            scope_paths=["Assets/Sample.cs"],
            expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        )
        original = self.source.read_bytes()

        with self.assertRaisesRegex(ValueError, "approval is missing, stale, revoked"):
            self.dispatch()

        self.assertFalse(self.application_path().exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_changed_source_revision_blocks_before_dispatch_marker(self):
        self.register_decision(
            scope_paths=["Assets/Sample.cs"],
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        )
        self.source.write_text(
            "public class Sample { public int Get() { return 2; } }\n",
            encoding="utf-8",
        )
        changed = self.source.read_bytes()

        with self.assertRaisesRegex(ValueError, "Project revision changed"):
            self.dispatch()

        self.assertFalse(self.application_path().exists())
        self.assertEqual(self.source.read_bytes(), changed)


if __name__ == "__main__":
    unittest.main()
