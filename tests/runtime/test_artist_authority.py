from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch

from unityagent.control_plane.artist_authority import ArtistAuthority, reviewed_artist_plan
from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.store.atomic_store import PersistenceError
from unityagent.runtime.reference_implementation.authority import ApprovalDecisionResolver
from unityagent.runtime.reference_implementation.contracts import ContractValidationError
from tests.runtime.reference_implementation.test_reference_implementation import contract_fixture


class ArtistAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task, self.approval, self.grant, self.action = contract_fixture()
        self.store = ApprovalDecisionStore(Path(self.temp.name))
        self.resolver = ApprovalDecisionResolver(self.store)
        self.resolver.register(self.approval)
        self.diff = [{"target": self.action.target["guid"], "property": self.action.property_path, "before": "40", "after": "43"}]
        self.binding = reviewed_artist_plan(task=self.task, action=self.action, command="artist.apply", plan_id="plan-test", exact_diff=self.diff)
        self.store.bind_artist_plan(self.approval.approval_decision_id, self.binding)

    def authority(self):
        return ArtistAuthority(task=self.task, approval=self.approval, grant=self.grant, action=self.action, resolver=self.resolver, store=self.store, binding=self.binding)

    def request(self, authority):
        return {"sessionId": authority.session_id, "nonce": "a" * 32, "projectRoot": self.task.project["root"], "command": "artist.apply", "planId": "plan-test", "expectedRevision": self.action.expected_revision, "approvalToken": authority.token, "exactDiff": copy.deepcopy(self.diff)}

    def test_exact_reviewed_binding_is_consumed_once_and_remains_used_after_restart(self):
        authority = self.authority()
        result = authority.authorize(self.request(authority))
        self.assertTrue(result["allowed"])
        self.assertTrue(result["reservationId"])
        self.assertFalse(authority.authorize(self.request(authority))["allowed"])
        self.store = ApprovalDecisionStore(Path(self.temp.name))
        self.resolver = ApprovalDecisionResolver(self.store)
        self.resolver.register(self.approval)
        restarted = self.authority()
        self.assertFalse(restarted.authorize(self.request(restarted))["allowed"])

    def test_nonempty_forged_token_and_changed_bindings_do_not_consume(self):
        for field, value in (("approvalToken", "forged"), ("projectRoot", "/another-project"), ("planId", "other"), ("expectedRevision", "stale"), ("command", "artist.cinematic"), ("sessionId", "unknown"), ("nonce", "short")):
            with self.subTest(field=field):
                authority = self.authority()
                request = self.request(authority)
                request[field] = value
                self.assertFalse(authority.authorize(request)["allowed"])
        authority = self.authority()
        request = self.request(authority)
        request["exactDiff"][0]["after"] = "44"
        self.assertFalse(authority.authorize(request)["allowed"])
        self.assertTrue(authority.authorize(self.request(authority))["allowed"])

    def test_revocation_is_rechecked_before_consumption(self):
        authority = self.authority()
        self.resolver.revoke(self.approval.approval_decision_id)
        self.assertFalse(authority.authorize(self.request(authority))["allowed"])

    def test_expired_decision_does_not_consume_the_reviewed_plan(self):
        authority = self.authority()
        with patch("unityagent.runtime.reference_implementation.authority.utc_now", return_value=datetime.max.replace(tzinfo=timezone.utc)):
            self.assertFalse(authority.authorize(self.request(authority))["allowed"])
        self.assertNotIn("artist_consumption", self.store.get(self.approval.approval_decision_id))

    def test_unreviewed_plan_is_not_bound_implicitly(self):
        path = self.store.layout.approval_decision(self.approval.approval_decision_id)
        record = json.loads(path.read_text(encoding="utf-8"))
        del record["artist_plan"]
        path.write_text(json.dumps(record), encoding="utf-8")
        authority = self.authority()
        self.assertFalse(authority.authorize(self.request(authority))["allowed"])
        self.assertNotIn("artist_plan", self.store.get(self.approval.approval_decision_id))

    def test_non_ascii_token_is_rejected_without_transport_exception(self):
        authority = self.authority()
        request = self.request(authority)
        request["approvalToken"] = "偽承認"
        self.assertFalse(authority.authorize(request)["allowed"])

    def test_authorization_and_revocation_share_resolver_guard_order(self):
        authority = self.authority()
        entered = threading.Event()
        completed = threading.Event()
        with self.resolver.execution_guard():
            thread = threading.Thread(target=lambda: (entered.set(), authority.authorize(self.request(authority)), completed.set()), daemon=True)
            thread.start()
            self.assertTrue(entered.wait(1))
            self.resolver.revoke(self.approval.approval_decision_id)
            self.assertFalse(completed.is_set())
        thread.join(timeout=3)
        self.assertTrue(completed.is_set())

    def test_parallel_authorization_has_one_winner(self):
        authority = self.authority()
        results = []
        threads = [threading.Thread(target=lambda: results.append(authority.authorize(self.request(authority)))) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(result["allowed"] for result in results), 1)

    def test_plan_binding_cannot_be_replaced_or_manufactured_by_transport(self):
        changed = copy.deepcopy(self.binding)
        changed["planId"] = "different-plan"
        with self.assertRaises(PersistenceError):
            self.store.bind_artist_plan(self.approval.approval_decision_id, changed)
        self.store.register(self.approval)
        self.assertEqual(self.store.get(self.approval.approval_decision_id)["artist_plan"], self.binding)

    def test_scope_and_action_value_must_match_reviewed_diff(self):
        for field, value in (("target", "unapproved"), ("property", "Light.intensity"), ("after", "49")):
            diff = copy.deepcopy(self.diff)
            diff[0][field] = value
            with self.subTest(field=field), self.assertRaises(ContractValidationError):
                reviewed_artist_plan(task=self.task, action=self.action, command="artist.apply", plan_id="plan-test", exact_diff=diff)

    def test_http_requires_signed_body_and_signs_bound_response(self):
        authority = self.authority()
        with authority:
            descriptor = json.loads(authority.descriptor_path.read_text(encoding="utf-8"))
            self.assertEqual(descriptor["projectRoot"], self.task.project["root"])
            payload = json.dumps(self.request(authority), separators=(",", ":")).encode()
            secret = bytes.fromhex(descriptor["secret"])
            signature = hmac.new(secret, b"request\n" + payload, hashlib.sha256).hexdigest()
            for forged in ("", "forged", "é" * 64):
                request = urllib.request.Request(descriptor["endpoint"], data=payload, headers={"X-UnityAgent-Signature": forged})
                with self.subTest(signature=forged), self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(request, timeout=3)
                self.assertEqual(rejected.exception.code, 403)
            request = urllib.request.Request(descriptor["endpoint"], data=payload, headers={"Content-Type": "application/json", "X-UnityAgent-Signature": signature})
            with urllib.request.urlopen(request, timeout=3) as response:
                raw = response.read()
                self.assertTrue(json.loads(raw)["allowed"])
                self.assertEqual(response.headers["X-UnityAgent-Signature"], hmac.new(secret, b"response\n" + raw, hashlib.sha256).hexdigest())
        self.assertFalse(authority.descriptor_path.exists())

    def test_unowned_descriptor_is_never_overwritten(self):
        authority = self.authority()
        authority.descriptor_path.parent.mkdir(parents=True, exist_ok=True)
        authority.descriptor_path.write_text("existing", encoding="utf-8")
        try:
            with self.assertRaises(FileExistsError):
                with authority:
                    pass
            self.assertEqual(authority.descriptor_path.read_text(encoding="utf-8"), "existing")
        finally:
            authority.descriptor_path.unlink()
