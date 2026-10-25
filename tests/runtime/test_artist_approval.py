from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from unityagent.control_plane.artist_authority import ArtistAuthority
from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.runtime.reference_implementation.authority import ApprovalDecisionResolver
from unityagent.runtime.reference_implementation.contracts import ContractValidationError


class ArtistPlanApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        (self.root / "Assets").mkdir()
        self.state = Path(self.temp.name) / "state"
        self.plane = SimpleNamespace(state_store=SimpleNamespace(layout=SimpleNamespace(root=self.state)))
        self.store = ApprovalDecisionStore(self.state)
        self.resolver = ApprovalDecisionResolver(self.store)
        self.diff = [{"target": "Director", "property": "marker", "before": "absent", "after": "1.5"}, {"target": "Director", "property": "binding", "before": "observed", "after": "Camera"}]
        self.editor = {"schemaVersion": "2.0", "product": "UnityArtistCLI", "command": "artist.cinematic", "status": "passed", "errors": [], "approvalRequired": True, "savePerformed": False, "planId": "artist-cinematic-plan-test", "revision": "revision-1", "baseRevision": "revision-1", "exactDiff": copy.deepcopy(self.diff), "mutationPaths": ["Assets/Fixture.unity", "Assets/Timeline.playable"], "contextReceipt": {"receivedContextId": "context-1", "receivedContextFingerprint": "fingerprint-1"}}

    def api(self):
        try:
            module = importlib.import_module("unityagent.control_plane.artist_approval")
        except ModuleNotFoundError:
            self.fail("general Artist Plan registration and explicit approval are not implemented")
        return module

    def register(self, **changes):
        values = dict(project_root=str(self.root), run_id="run-1", command="artist.cinematic", editor_plan=self.editor, context_id="context-1", context_fingerprint="fingerprint-1", scope={"allowed_paths": ["Assets"], "prohibited_paths": ["ProjectSettings"]})
        values.update(changes)
        return self.api().register_artist_plan(self.plane, **values)

    def approved(self):
        plan = self.register()
        decision = self.api().approve_artist_plan(self.plane, plan["plan_id"])
        return plan, decision

    def request(self, authority):
        binding = authority.binding
        request = {"sessionId": authority.session_id, "nonce": "a" * 32, "projectRoot": str(self.root), "command": "artist.cinematic", "planId": self.editor["planId"], "expectedRevision": "revision-1", "approvalToken": authority.token, "exactDiff": copy.deepcopy(self.diff), "context": {"contextId": binding["receivedContextId"], "contextFingerprint": binding["receivedContextFingerprint"], "projectRoot": binding["projectRoot"], "runId": binding["runId"]}}
        if binding["command"] != "artist.evaluate":
            request["mutationPaths"] = copy.deepcopy(binding["mutationPaths"])
        return request

    def test_registration_is_immutable_and_does_not_approve(self):
        plan = self.register()
        self.assertEqual(plan["exact_diff"], self.diff)
        self.assertEqual(list(self.state.rglob("*approval*.json")), [])
        self.assertEqual(self.register(), plan)
        changed = copy.deepcopy(self.editor)
        changed["exactDiff"][0]["after"] = "different"
        with self.assertRaises(Exception):
            self.register(editor_plan=changed)

    def test_observed_mutation_paths_are_required_canonical_and_within_reviewed_scope(self):
        for paths in (None, [], "Assets/Fixture.unity", [""], ["/Assets/Fixture.unity"], ["C:/Assets/Fixture.unity"], ["Assets/../Packages/Fixture.asset"], ["Assets//Fixture.unity"], ["Assets/./Fixture.unity"], ["Assets\\Fixture.unity"], ["Assets/Fixture.unity/"], [" Assets/Fixture.unity"], ["Packages/Fixture.asset"], ["Assets"], ["Assets/Fixture.unity", "Assets/Fixture.unity"]):
            editor = copy.deepcopy(self.editor)
            if paths is None:
                editor.pop("mutationPaths")
            else:
                editor["mutationPaths"] = paths
            with self.subTest(paths=paths), self.assertRaises(ContractValidationError):
                self.register(editor_plan=editor)
        for scope in ({"allowed_paths": ["Assets/Other"], "prohibited_paths": []}, {"allowed_paths": ["Assets"], "prohibited_paths": ["Assets/Timeline.playable"]}, {"allowed_paths": [], "prohibited_paths": []}):
            with self.subTest(scope=scope), self.assertRaises(ContractValidationError):
                self.register(scope=scope)
        plan, decision = self.approved()
        self.assertEqual(plan["mutation_paths"], self.editor["mutationPaths"])
        self.assertEqual(decision["binding"]["mutationPaths"], self.editor["mutationPaths"])

    def test_scope_uses_directory_boundaries_and_rechecks_paths_before_approval(self):
        editor = copy.deepcopy(self.editor)
        editor["mutationPaths"] = ["Assets/AllowedExtra/Fixture.unity"]
        with self.assertRaises(ContractValidationError):
            self.register(editor_plan=editor, scope={"allowed_paths": ["Assets/Allowed"], "prohibited_paths": []})
        plan = self.register()
        path = self.api()._plan_path(self.state, plan["plan_id"])
        from unityagent.persistence.store.atomic_store import read_json, sha256_json
        changed = read_json(path)
        changed["mutation_paths"] = ["Packages/Unreviewed.asset"]
        changed["plan_digest"] = sha256_json({key: value for key, value in changed.items() if key != "plan_digest"})
        import json
        path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(ContractValidationError):
            self.api().approve_artist_plan(self.plane, plan["plan_id"])

    def directory_link(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            try:
                import _winapi
                _winapi.CreateJunction(str(target), str(link))
            except (ImportError, OSError) as exc:
                self.skipTest("directory link privilege unavailable: " + str(exc))

    def test_mutation_path_symlink_escape_is_rejected(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        link = self.root / "Assets/Linked"
        self.directory_link(link, outside)
        editor = copy.deepcopy(self.editor)
        editor["mutationPaths"] = ["Assets/Linked/Timeline.playable"]
        with self.assertRaises(ContractValidationError):
            self.register(editor_plan=editor)

    def test_approval_and_resolver_recheck_link_escape_after_registration(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        link = self.root / "Assets/Linked"
        link.mkdir()
        editor = copy.deepcopy(self.editor)
        editor["mutationPaths"] = ["Assets/Linked/Timeline.playable"]
        plan = self.register(editor_plan=editor)
        decision = self.api().approve_artist_plan(self.plane, plan["plan_id"])
        link.rmdir()
        self.directory_link(link, outside)
        with self.assertRaises(ContractValidationError):
            self.api().approve_artist_plan(self.plane, plan["plan_id"])
        with self.assertRaises(ContractValidationError):
            self.resolver.resolve_artist_plan(decision["approval_decision_id"], project_root=str(self.root), run_id="run-1", plan_id=plan["plan_id"])

    def test_explicit_approval_resolves_general_diff_and_is_consumed_once(self):
        plan, decision = self.approved()
        trusted = self.resolver.resolve_artist_plan(decision["approval_decision_id"], project_root=str(self.root), run_id="run-1", plan_id=plan["plan_id"])
        authority = ArtistAuthority.for_plan(resolver=self.resolver, store=self.store, binding=trusted["binding"], decision=trusted)
        self.assertIsNone(authority.reservation_id)
        result = authority.authorize(self.request(authority))
        self.assertTrue(result["allowed"])
        self.assertEqual(authority.reservation_id, result["reservationId"])
        self.assertEqual(self.store.get(decision["approval_decision_id"])["artist_consumption"]["reservation_id"], authority.reservation_id)
        self.assertFalse(authority.authorize(self.request(authority))["allowed"])
        restarted = ArtistAuthority.for_plan(resolver=ApprovalDecisionResolver(self.store), store=self.store, binding=trusted["binding"], decision=trusted)
        self.assertFalse(restarted.authorize(self.request(restarted))["allowed"])

    def test_plan_and_context_must_be_observed_and_unmodified(self):
        for field, value in (("schemaVersion", "1.0"), ("status", "failed"), ("approvalRequired", False), ("errors", [{"code": "ERROR"}]), ("baseRevision", ""), ("revision", "different"), ("planId", "../escape"), ("command", "artist.inspect"), ("savePerformed", True), ("contextReceipt", {})):
            changed = copy.deepcopy(self.editor)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises((ContractValidationError, ValueError)):
                self.register(editor_plan=changed)
        for values in ({"context_id": "other"}, {"context_fingerprint": "other"}, {"context_id": ""}):
            with self.subTest(values=values), self.assertRaises(ContractValidationError):
                self.register(**values)

    def test_exact_diff_requires_nonempty_unique_pairs_and_scope_agreement(self):
        for diff in ([], [self.diff[0], self.diff[0]], [{**self.diff[0], "before": ""}], [{**self.diff[0], "after": 1}], [{**self.diff[0], "extra": "value"}]):
            changed = copy.deepcopy(self.editor)
            changed["exactDiff"] = diff
            with self.subTest(diff=diff), self.assertRaises(ContractValidationError):
                self.register(editor_plan=changed)
        with self.assertRaises(ContractValidationError):
            self.register(scope={"exact_pairs": [{"target": "other", "property": "marker"}]})

    def test_resolver_rejects_wrong_run_project_plan_revocation_and_tampering(self):
        plan, decision = self.approved()
        ref = decision["approval_decision_id"]
        for values in ({"project_root": str(self.root / "other"), "run_id": "run-1", "plan_id": plan["plan_id"]}, {"project_root": str(self.root), "run_id": "other", "plan_id": plan["plan_id"]}, {"project_root": str(self.root), "run_id": "run-1", "plan_id": "other"}):
            with self.subTest(values=values), self.assertRaises(ContractValidationError):
                self.resolver.resolve_artist_plan(ref, **values)
        changed = copy.deepcopy(decision)
        changed["binding"]["receivedContextId"] = "forged"
        self.store.register(changed)
        with self.assertRaises(ContractValidationError):
            self.resolver.resolve_artist_plan(ref, project_root=str(self.root), run_id="run-1", plan_id=plan["plan_id"])
        self.store.register(decision)
        self.resolver.revoke(ref)
        self.store.register(decision)
        with self.assertRaises(ContractValidationError):
            self.resolver.resolve_artist_plan(ref, project_root=str(self.root), run_id="run-1", plan_id=plan["plan_id"])

    def test_expired_approval_and_changed_transport_diff_do_not_execute(self):
        plan = self.register()
        with self.assertRaises(ContractValidationError):
            self.api().approve_artist_plan(self.plane, plan["plan_id"], expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
        decision = self.api().approve_artist_plan(self.plane, plan["plan_id"])
        authority = ArtistAuthority.for_plan(resolver=self.resolver, store=self.store, binding=decision["binding"], decision=decision)
        changed = self.request(authority)
        changed["exactDiff"][1]["after"] = "unreviewed"
        self.assertFalse(authority.authorize(changed)["allowed"])
        self.resolver.revoke(decision["approval_decision_id"])
        self.assertFalse(authority.authorize(self.request(authority))["allowed"])

    def test_authority_cannot_substitute_a_context_binding(self):
        _, decision = self.approved()
        changed = copy.deepcopy(decision["binding"])
        changed["receivedContextFingerprint"] = "different"
        with self.assertRaises(ContractValidationError):
            ArtistAuthority.for_plan(resolver=self.resolver, store=self.store, binding=changed, decision=decision)

    def capture(self):
        return {**copy.deepcopy(self.editor), "command": "artist.capture", "approvalRequired": False, "verified": True, "captureId": "artist-capture-test", "planId": "", "exactDiff": [], "mutationPaths": [], "evidence": ["visual_capture", "capture_manifest", "camera_binding:Shot Camera"]}

    def register_review(self, **changes):
        values = {"command": "artist.evaluate", "editor_plan": self.capture(), "review": {"captureId": "artist-capture-test", "decision": "accepted", "notes": ""}}
        values.update(changes)
        return self.register(**values)

    def test_evaluate_requires_explicit_review_approval_and_authenticates_three_review_fields(self):
        plan = self.register_review()
        self.assertEqual(plan["exact_diff"], [])
        self.assertEqual(plan["mutation_paths"], [])
        decision = self.api().approve_artist_plan(self.plane, plan["plan_id"])
        authority = ArtistAuthority.for_plan(resolver=self.resolver, store=self.store, binding=decision["binding"], decision=decision)
        self.assertNotIn("mutationPaths", decision["binding"])
        request = {**self.request(authority), "command": "artist.evaluate", "planId": "artist-capture-test", "exactDiff": [], "review": copy.deepcopy(plan["review"])}
        for field, value in (("captureId", "other"), ("decision", "rejected"), ("notes", "forged")):
            changed = copy.deepcopy(request)
            changed["review"][field] = value
            with self.subTest(field=field):
                self.assertFalse(authority.authorize(changed)["allowed"])
        missing = copy.deepcopy(request)
        missing.pop("review")
        self.assertFalse(authority.authorize(missing)["allowed"])
        self.assertIsNone(authority.reservation_id)
        result = authority.authorize(request)
        self.assertTrue(result["allowed"])
        self.assertEqual(authority.reservation_id, result["reservationId"])
        self.assertFalse(authority.authorize(request)["allowed"])

    def test_evaluate_rejects_unobserved_capture_invalid_review_and_mutation_diff(self):
        for field, value in (("verified", False), ("captureId", ""), ("command", "artist.plan"), ("evidence", []), ("exactDiff", self.diff)):
            capture = self.capture()
            capture[field] = value
            with self.subTest(field=field), self.assertRaises(ContractValidationError):
                self.register_review(editor_plan=capture)
        for review in ({"captureId": "artist-capture-test", "decision": "automatic", "notes": ""}, {"captureId": "other", "decision": "accepted", "notes": ""}, {"captureId": "artist-capture-test", "decision": "accepted"}):
            with self.subTest(review=review), self.assertRaises(ContractValidationError):
                self.register_review(review=review)

    def test_resolver_checks_expiry_kind_status_human_decision_and_digest(self):
        plan, decision = self.approved()
        for field, value in (("expires_at", "2000-01-01T00:00:00+00:00"), ("expires_at", "not-a-time"), ("kind", "hot_reload"), ("schema_version", "other"), ("status", "inactive"), ("human_decision", "rejected"), ("decision_digest", "forged")):
            changed = copy.deepcopy(decision)
            changed[field] = value
            self.store.register(changed)
            with self.subTest(field=field, value=value), self.assertRaises(ContractValidationError):
                self.resolver.resolve_artist_plan(decision["approval_decision_id"], project_root=str(self.root), run_id="run-1", plan_id=plan["plan_id"])
        self.store.register(decision)
        self.assertEqual(self.resolver.resolve_artist_plan(decision["approval_decision_id"], project_root=str(self.root), run_id="run-1", plan_id=plan["plan_id"]), decision)

    def test_authority_rechecks_expiry_after_session_creation(self):
        from unittest.mock import patch
        from unityagent.runtime.contracts import artist_plan
        _, decision = self.approved()
        authority = ArtistAuthority.for_plan(resolver=self.resolver, store=self.store, binding=decision["binding"], decision=decision)
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        class FutureClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return future
        with patch.object(artist_plan, "datetime", FutureClock):
            self.assertFalse(authority.authorize(self.request(authority))["allowed"])
        self.assertIsNone(authority.reservation_id)
        self.assertNotIn("artist_consumption", self.store.get(decision["approval_decision_id"]))
