from __future__ import annotations

import copy
import json
import unittest

from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand, build_artist_pipeline_command
from unityagent.runtime.tooling.providers.unity_cli.artist_result_mapper import normalize_artist_pipeline_result
from tests.subagent.artist import test_artist_execution as fixture


class ArtistMutationMapperTests(unittest.TestCase):
    def setUp(self):
        case = next(case for case in fixture.BASELINE["commands"] if case["command"] == "apply")
        self.editor = copy.deepcopy(case["editor_result"])
        self.editor.update(authoritySessionId="a" * 32, authorityNonce="b" * 32, authorityReservationId="c" * 32)
        self.editor["contextReceipt"] = {"receivedContextId": "context-test", "receivedContextFingerprint": "fingerprint-test", "projectRoot": str(fixture.ROOT), "runId": "run-test"}
        context = json.dumps({"contextId": "context-test", "contextFingerprint": "fingerprint-test", "projectRoot": str(fixture.ROOT), "runId": "run-test"})
        self.command = ArtistCommand("apply", plan_id=self.editor["planId"], expected_revision=self.editor["baseRevision"], approval_token="d" * 64, context_json=context)
        self.authorization = {"command": "artist.apply", "planId": self.command.plan_id, "expectedRevision": self.command.expected_revision, "exactDiff": copy.deepcopy(self.editor["exactDiff"]), "token": self.command.approval_token, "sessionId": "a" * 32, "reservationId": "c" * 32}
        self.authorization["mutationPaths"] = ["Assets/Fixture.unity"]
        self.editor["mutationPaths"] = ["Assets/Fixture.unity"]

    def map(self):
        return normalize_artist_pipeline_result(exit_code=0, stdout=fixture.output(self.editor), command=self.command, project_root=fixture.ROOT, unity_version="6000.3.12f1", render_pipeline="builtin", expected_context_id="context-test", expected_context_fingerprint="fingerprint-test", expected_run_id="run-test", authorization=self.authorization)

    def test_authenticated_mutation_transports_context_and_exact_diff(self):
        self.assertIn("--context-json", build_artist_pipeline_command("unity", fixture.ROOT, self.command, authorization=self.authorization).argv)
        result = self.map()
        self.assertEqual(result["status"], "passed", result)
        self.assertIn("mutation_evidence", result["evidence"])
        self.assertEqual(result["payload"]["exactDiff"], self.editor["exactDiff"])

    def test_forged_receipt_unreviewed_diff_and_other_run_never_pass(self):
        for field, value in (("authoritySessionId", "other"), ("authorityReservationId", "forged"), ("authorityNonce", ""), ("exactDiff", []), ("revision", self.editor["baseRevision"]), ("verified", False)):
            original = self.editor[field]
            self.editor[field] = value
            self.assertEqual(self.map()["status"], "failed", field)
            self.editor[field] = original
        self.editor["contextReceipt"]["runId"] = "another-run"
        self.assertEqual(self.map()["status"], "failed")

    def test_nonempty_token_without_the_exact_binding_never_builds_mutation(self):
        with self.assertRaises(PermissionError):
            build_artist_pipeline_command("unity", fixture.ROOT, self.command)
        self.authorization["planId"] = "different-plan"
        with self.assertRaises(PermissionError):
            build_artist_pipeline_command("unity", fixture.ROOT, self.command, authorization=self.authorization)

    def test_unobserved_or_different_mutation_paths_never_pass(self):
        for paths in (None, [], ["Assets/Other.unity"]):
            self.editor["mutationPaths"] = paths
            self.assertEqual(self.map()["status"], "failed")
