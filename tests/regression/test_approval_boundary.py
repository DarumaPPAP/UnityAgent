"""ApprovalDecisionStoreの取消、Plan束縛、単回消費を実FSで検証する。"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import hashlib
import hmac
import json
import secrets
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from unityagent.control_plane.artist_approval import register_artist_plan, approve_artist_plan
from unityagent.control_plane.artist_authority import ArtistAuthority
from unityagent.control_plane.artist_execution import execute_artist
from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.runtime.reference_implementation.contracts import ContractValidationError
from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand

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


class SignedAuthorityTests(unittest.TestCase):
    """Editorの代わりに実署名HTTPを送る。Editor内部のApplyはP1で検証する。"""

    def setUp(self):
        temporary = TemporaryDirectory(prefix="ua-auth-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        (self.project / "Assets").mkdir(parents=True)
        self.source = self.project / "Assets/Sample.cs"
        self.source.write_bytes(b"class Sample {}\n")
        self.plane = UnityAgentControlPlane(self.root / "state")
        self.scope = {"allowed_paths": ["Assets"], "prohibited_paths": ["Packages", "ProjectSettings"]}
        observed_plan = {"schemaVersion": "2.0", "product": "UnityArtistCLI", "command": "artist.plan", "status": "passed", "errors": [], "approvalRequired": True, "savePerformed": False, "contextReceipt": {"receivedContextId": "ctx-A", "receivedContextFingerprint": "fingerprint-A"}, "baseRevision": "revision-A", "revision": "revision-A", "planId": "plan-A", "exactDiff": [{"target": "sample-target", "property": "value", "before": "1", "after": "2"}], "mutationPaths": ["Assets/Sample.cs"]}
        self.plan = register_artist_plan(self.plane, str(self.project), "run-A", "artist.apply", observed_plan, "ctx-A", "fingerprint-A", self.scope)
        self.decision = approve_artist_plan(self.plane, "plan-A")
        self.store = self.plane.approval_resolver.store

    def authority(self):
        return ArtistAuthority.for_plan(resolver=self.plane.approval_resolver, store=self.store, binding=self.decision["binding"], decision=self.decision)

    def send(self, authority, *, project=None, signature_valid=True):
        descriptor = read_json(authority.descriptor_path)
        request = {"sessionId": descriptor["sessionId"], "nonce": secrets.token_hex(16), "projectRoot": project or str(self.project), "command": "artist.apply", "planId": "plan-A", "expectedRevision": "revision-A", "approvalToken": authority.token, "exactDiff": self.plan["exact_diff"], "context": {"contextId": "ctx-A", "contextFingerprint": "fingerprint-A", "projectRoot": self.plan["project_root"], "runId": "run-A"}, "mutationPaths": ["Assets/Sample.cs"]}
        body = json.dumps(request, separators=(",", ":")).encode()
        secret = bytes.fromhex(descriptor["secret"])
        signature = hmac.new(secret, b"request\n" + body, hashlib.sha256).hexdigest() if signature_valid else "0" * 64
        transport = Request(descriptor["endpoint"], data=body, headers={"Content-Type": "application/json", "X-UnityAgent-Signature": signature})
        with urlopen(transport, timeout=5) as response:
            raw = response.read()
            self.assertEqual(response.headers["X-UnityAgent-Signature"], hmac.new(secret, b"response\n" + raw, hashlib.sha256).hexdigest())
            return json.loads(raw)

    def assert_unconsumed_and_unchanged(self):
        self.assertNotIn("artist_consumption", self.store.get(self.decision["approval_decision_id"]))
        self.assertEqual(self.source.read_bytes(), b"class Sample {}\n")

    def test_signed_request_consumes_once_and_response_is_authenticated(self):
        authority = self.authority()
        with authority:
            first = self.send(authority)
            self.assertTrue(first["allowed"])
            self.assertTrue(first["reservationId"])
            second = self.send(authority)
            self.assertFalse(second["allowed"])
            self.assertIn("already", second["reason"])
        persisted = ApprovalDecisionStore(self.root / "state").get(self.decision["approval_decision_id"])
        self.assertEqual(persisted["artist_consumption"]["reservation_id"], first["reservationId"])
        self.assertFalse(authority.descriptor_path.exists())

    def test_invalid_signature_cannot_consume_or_block_later_valid_request(self):
        with self.authority() as authority:
            with self.assertRaises(HTTPError) as captured:
                self.send(authority, signature_valid=False)
            self.assertEqual(captured.exception.code, 403)
            captured.exception.close()
            self.assert_unconsumed_and_unchanged()
            self.assertTrue(self.send(authority)["allowed"])

    def test_signed_other_project_is_rejected_without_consumption(self):
        with self.authority() as authority:
            response = self.send(authority, project=str(self.root / "other"))
            self.assertFalse(response["allowed"])
            self.assert_unconsumed_and_unchanged()
            self.assertTrue(self.send(authority)["allowed"])

    def test_revocation_after_session_open_stops_signed_request(self):
        with self.authority() as authority:
            self.store.revoke(self.decision["approval_decision_id"])
            response = self.send(authority)
            self.assertFalse(response["allowed"])
            self.assertIn("revoked", response["reason"])
            self.assert_unconsumed_and_unchanged()

    def test_expiry_after_session_open_stops_signed_request(self):
        with self.authority() as authority:
            expiry = datetime.fromisoformat(self.decision["expires_at"])
            # 時刻だけを進め、署名・Resolver・永続消費の実処理は維持する。
            with patch("unityagent.runtime.contracts.artist_plan.datetime", wraps=datetime) as clock:
                clock.now.return_value = expiry
                response = self.send(authority)
            self.assertFalse(response["allowed"])
            self.assertIn("expired", response["reason"])
            self.assert_unconsumed_and_unchanged()

    def dispatch(self, broker, *, project=None):
        # Context選択とEditor発見は対象外。承認判定から実Dispatch境界までは置換しない。
        session = {"scope": self.scope, "domain": "visual_art", "manifest_ref": "test-context.json", "manifest": {"materialized_context": {"context_id": "ctx-A", "context_fingerprint": {"value": "fingerprint-A"}, "specialist_context": {"profile_id": "artist_subagent"}}}}
        with patch("unityagent.control_plane.artist_execution.discover_environment", return_value={}), patch("unityagent.control_plane.artist_execution._context", return_value=session), patch.object(self.plane.broker, "dispatch", broker):
            return execute_artist(self.plane, str(project or self.project), "run-A", ArtistCommand(name="apply", plan_id="plan-A"), definition_fingerprint={}, approval_ref=self.decision["approval_decision_id"])

    def test_control_plane_valid_approval_reaches_dispatch_with_live_authority(self):
        class DispatchObserved(Exception):
            pass

        def observe(request, snapshot, **parameters):
            self.assertEqual(request["approval_ref"], self.decision["approval_decision_id"])
            authority = parameters["provider_arguments"]["unity_cli"]["artist_authority"]
            self.assertTrue(self.send(authority)["allowed"])
            raise DispatchObserved()

        broker = Mock(side_effect=observe)
        with self.assertRaises(DispatchObserved):
            self.dispatch(broker)
        broker.assert_called_once()
        self.assertEqual(self.source.read_bytes(), b"class Sample {}\n")

    def test_control_plane_revoked_approval_stops_before_dispatch(self):
        self.store.revoke(self.decision["approval_decision_id"])
        broker = Mock()
        with self.assertRaisesRegex(ContractValidationError, "revoked"):
            self.dispatch(broker)
        broker.assert_not_called()
        self.assert_unconsumed_and_unchanged()

    def test_control_plane_project_binding_stops_before_dispatch(self):
        broker = Mock()
        with self.assertRaisesRegex(ContractValidationError, "binding differs"):
            self.dispatch(broker, project=self.root / "other-project")
        broker.assert_not_called()
        self.assert_unconsumed_and_unchanged()

    def test_control_plane_expired_approval_stops_before_dispatch(self):
        broker = Mock()
        with patch("unityagent.runtime.contracts.artist_plan.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime.fromisoformat(self.decision["expires_at"])
            with self.assertRaisesRegex(ContractValidationError, "expired"):
                self.dispatch(broker)
        broker.assert_not_called()
        self.assert_unconsumed_and_unchanged()


if __name__ == "__main__":
    unittest.main()
