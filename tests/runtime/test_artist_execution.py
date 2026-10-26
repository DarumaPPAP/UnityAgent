from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand
from tests.runtime import test_artist_command_adapter as boundary_fixture
from tests.runtime.test_control_plane import fingerprint


class ArtistExecutionTests(unittest.TestCase):
    def setUp(self):
        self.boundary = boundary_fixture.ArtistProviderBoundaryTests()
        self.boundary.setUp()
        self.addCleanup(self.boundary.doCleanups)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.plane = UnityAgentControlPlane(Path(self.temp.name) / "state")
        self.root = str(self.boundary.root)
        self.snapshot = copy.deepcopy(self.boundary.snapshot)
        self.calls = []

    def api(self):
        try:
            return importlib.import_module("unityagent.control_plane.artist_execution")
        except ModuleNotFoundError:
            self.fail("Artist Entry is not connected to Control Plane Broker and Persistence")

    def fake_execute(self, request, context, arguments):
        command = arguments["artist_command"]
        received = arguments["specialist_execution_context"]
        self.calls.append((request, command, received))
        editor = {"schemaVersion": "2.0", "product": "UnityArtistCLI", "command": "artist." + command.name, "status": "passed", "errors": [], "approvalRequired": False, "savePerformed": False, "verified": True, "planId": "", "revision": "revision-1", "baseRevision": "revision-1", "exactDiff": [], "evidence": ["visual_art_inspection", "pipeline_support_fact"], "contextReceipt": {"receivedContextId": received["context_id"], "receivedContextFingerprint": received["context_fingerprint"]}}
        if command.name == "plan":
            editor.update(planId="artist-plan-entry", approvalRequired=True, mutationPaths=["Assets/Fixture.unity"], exactDiff=[{"target": "Key", "property": "intensity", "before": "1", "after": "2"}])
        if command.name == "capture":
            editor.update(captureId="artist-capture-entry", evidence=["visual_capture", "capture_manifest", "camera_binding:Main Camera"])
        authority = arguments.get("artist_authority")
        if authority is not None:
            binding = authority.binding
            auth_request = {"sessionId": authority.session_id, "nonce": "a" * 32, "projectRoot": self.root, "command": binding["command"], "planId": binding["planId"], "expectedRevision": binding["expectedRevision"], "approvalToken": authority.token, "exactDiff": binding["exactDiff"]}
            auth_request["context"] = json.loads(command.context_json)
            if command.name == "evaluate":
                auth_request["review"] = binding["review"]
            else:
                auth_request["mutationPaths"] = binding["mutationPaths"]
            self.assertTrue(authority.authorize(auth_request)["allowed"])
        return {"status": "passed", "failure_class": None, "provider_ref": "unity_cli", "evidence": request["required_evidence"], "payload": editor, "received_context_id": received["context_id"], "received_context_fingerprint": received["context_fingerprint"]}

    def execute(self, command, **kwargs):
        api = self.api()
        class Provider:
            execute = staticmethod(self.fake_execute)
            def __init__(self, *args, **kwargs):
                pass
        with patch.object(api, "discover_environment", return_value=self.snapshot), patch.object(api, "UnityCliProvider", Provider):
            return api.execute_artist(self.plane, self.root, "artist-entry-run", command, definition_fingerprint=fingerprint(), **kwargs)

    def test_inspect_routes_through_broker_with_materialized_context_and_durable_evidence(self):
        result = self.execute(ArtistCommand("inspect"))
        self.assertEqual(result["status"], "completed", result)
        self.assertTrue(result["durable"])
        record = self.plane.evidence_store.get(result["evidence_refs"][0])
        self.assertEqual(record["durability"], "durable")
        session = json.loads(self.api()._session_path(self.plane, "artist-entry-run").read_text(encoding="utf-8"))
        self.assertLessEqual(session["manifest"]["budget_report"]["selected_artifacts"], 14)
        self.assertEqual(session["manifest"]["budget_report"]["decision"], "within_budget")
        request, command, received = self.calls[0]
        self.assertEqual(received["specialist_context"]["profile_id"], "artist_subagent")
        self.assertEqual(json.loads(command.context_json)["contextId"], received["context_id"])
        self.assertEqual(received["run_id"], "artist-entry-run")

    def test_plan_requires_explicit_approve_before_apply_and_consumption_rejects_replay(self):
        planned = self.execute(ArtistCommand("plan", request_json='{"setLightIntensity":true,"targetName":"Key","lightIntensity":2}'))
        self.assertEqual(planned["approval_plan_id"], "artist-plan-entry")
        with self.assertRaises(ValueError):
            self.execute(ArtistCommand("apply", plan_id="artist-plan-entry"))
        decision = self.api().approve_artist_execution(self.plane, self.root, "artist-entry-run", "artist-plan-entry")
        applied = self.execute(ArtistCommand("apply", plan_id="artist-plan-entry"), approval_ref=decision["approval_decision_id"])
        self.assertEqual(applied["status"], "completed", applied)
        evidence = self.plane.evidence_store.get(applied["evidence_refs"][0])
        self.assertEqual((evidence["safety_strength"], evidence["evidence_strength"]), (5, 5))
        self.assertEqual(self.calls[0][2]["context_fingerprint"], self.calls[-1][2]["context_fingerprint"])
        with self.assertRaises(ValueError):
            self.execute(ArtistCommand("apply", plan_id="artist-plan-entry"), approval_ref=decision["approval_decision_id"])

    def test_failed_mutation_does_not_restore_consumed_control_plane_approval(self):
        self.execute(ArtistCommand("plan", request_json='{"setLightIntensity":true,"targetName":"Key","lightIntensity":2}'))
        decision = self.api().approve_artist_execution(self.plane, self.root, "artist-entry-run", "artist-plan-entry")
        successful_boundary = self.fake_execute

        def fail_after_authorization(request, arguments, received):
            result = successful_boundary(request, arguments, received)
            result.update(status="failed", failure_class="execution_failed", reason="injected after authorization", evidence=[])
            return result

        with patch.object(self, "fake_execute", side_effect=fail_after_authorization):
            result = self.execute(ArtistCommand("apply", plan_id="artist-plan-entry"), approval_ref=decision["approval_decision_id"])
        self.assertNotEqual(result["status"], "completed")
        self.assertIsNotNone(self.plane.approval_resolver.store.get(decision["approval_decision_id"])["artist_consumption"])
        with self.assertRaisesRegex(ValueError, "already"):
            self.execute(ArtistCommand("apply", plan_id="artist-plan-entry"), approval_ref=decision["approval_decision_id"])

    def test_unobserved_partial_result_is_preserved_with_blocked_durable_state(self):
        self.execute(ArtistCommand("plan", request_json='{"setLightIntensity":true,"targetName":"Key","lightIntensity":2}'))
        decision = self.api().approve_artist_execution(self.plane, self.root, "artist-entry-run", "artist-plan-entry")
        successful_boundary = self.fake_execute

        def timeout_after_authorization(request, arguments, received):
            result = successful_boundary(request, arguments, received)
            result.update(status="failed", failure_class="not_observed", reason="injected missing observation after authorization", evidence=[])
            return result

        with patch.object(self, "fake_execute", side_effect=timeout_after_authorization):
            result = self.execute(ArtistCommand("apply", plan_id="artist-plan-entry"), approval_ref=decision["approval_decision_id"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["provider_result"]["failure_class"], "not_observed")
        self.assertTrue(result["durable"])
        self.assertEqual(self.plane.state_store.load_execution_state("artist-entry-run")["status"], "blocked")
        with self.assertRaisesRegex(ValueError, "already"):
            self.execute(ArtistCommand("apply", plan_id="artist-plan-entry"), approval_ref=decision["approval_decision_id"])

    def test_evaluate_without_approval_creates_review_plan_without_dispatch_or_human_record(self):
        captured = self.execute(ArtistCommand("capture", request_json='{"captureCameraName":"Main Camera"}'))
        self.assertEqual(captured["status"], "completed", captured)
        calls = len(self.calls)
        review = self.execute(ArtistCommand("evaluate", capture_id="artist-capture-entry", decision="accepted"))
        self.assertEqual(review["status"], "planned", review)
        self.assertEqual(len(self.calls), calls)
        decision = self.api().approve_artist_execution(self.plane, self.root, "artist-entry-run", review["approval_plan_id"])
        evaluated = self.execute(ArtistCommand("evaluate", capture_id="artist-capture-entry", decision="accepted"), approval_ref=decision["approval_decision_id"])
        self.assertEqual(evaluated["status"], "completed", evaluated)

    def test_untrusted_context_token_and_cross_run_approval_are_rejected_before_dispatch(self):
        for command in (ArtistCommand("inspect", context_json='{"contextId":"forged"}'), ArtistCommand("apply", plan_id="x", approval_token="forged")):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.execute(command)
        self.assertEqual(self.calls, [])

    def test_prohibited_policy_blocks_artist_before_provider_dispatch(self):
        api = self.api()
        with patch.object(api, "policy_for_capability", return_value={"default_permission": "prohibited"}, create=True):
            with self.assertRaisesRegex(ValueError, "Policy"):
                self.execute(ArtistCommand("inspect"))
        self.assertEqual(self.calls, [])

    def test_cinematic_context_preserves_required_contracts_within_existing_budget(self):
        result = self.execute(ArtistCommand("cinematic", operation="inspect"), domain="cinematic")
        self.assertEqual(result["status"], "completed", result)
        session = json.loads(self.api()._session_path(self.plane, "artist-entry-run").read_text(encoding="utf-8"))
        self.assertEqual(session["domain"], "cinematic")
        self.assertLessEqual(session["manifest"]["budget_report"]["selected_artifacts"], 14)
        revisions = session["manifest"]["materialized_context"]["context_fingerprint"]["selected_source_revisions"]
        refs = {item["ref"] for item in revisions}
        self.assertIn("subagent/artist_subagent/contracts/capability-contracts.yaml", refs)
        self.assertIn("subagent/artist_subagent/contracts/backend-surface-contract.yaml", refs)
        self.assertIn("src/unityagent/context/retrieval/knowledge/visual/unity-artist-cli.yaml", refs)
        with self.assertRaises(ValueError):
            self.execute(ArtistCommand("inspect"), domain="visual_art")

    def test_cinematic_director_change_requires_a_new_run(self):
        self.execute(ArtistCommand("cinematic", operation="inspect", request_json='{"directorName":"Director A"}'))
        calls = len(self.calls)
        with self.assertRaisesRegex(ValueError, "Director"):
            self.execute(ArtistCommand("cinematic", operation="plan", request_json='{"directorName":"Director B","trackKind":"activation","trackName":"Track"}'))
        self.assertEqual(len(self.calls), calls)

    def test_unbound_cinematic_inspection_context_cannot_be_reused_for_mutation(self):
        self.execute(ArtistCommand("cinematic", operation="inspect"))
        with self.assertRaisesRegex(ValueError, "Director"):
            self.execute(ArtistCommand("cinematic", operation="plan", request_json='{"directorName":"Director A","trackKind":"activation","trackName":"Track"}'))
