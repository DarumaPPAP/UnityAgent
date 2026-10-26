"""実Editor Gateが偽陽性を返さないための入力と結果検証。"""
import unittest
import contextlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from tools import run_artist_cinematic_live as runner


class CinematicLiveRunnerTests(unittest.TestCase):
    def test_requests_cover_allowlisted_kinds_and_shot_reference_updates(self):
        cases = runner.cinematic_cases("owned")
        self.assertEqual({request["trackKind"] for _, request in cases}, {"binding", "activation", "animation", "control", "signal", "marker", "cinemachine_shot", "shot"})
        activation = next(request for name, request in cases if name == "activation")
        binding = next(request for name, request in cases if name == "binding")
        self.assertEqual(binding["trackName"], activation["trackName"])
        for kind in ("shot", "cinemachine_shot"):
            created = next(request for name, request in cases if name == kind)
            updated = next(request for name, request in cases if name == kind + "-update")
            self.assertEqual(created["trackName"], updated["trackName"])
            self.assertNotEqual(created["bindingTargetName"], updated["bindingTargetName"])
            self.assertNotEqual(created["clipStart"], updated["clipStart"])

    def test_apply_requires_actual_verified_mutation_and_exact_paths(self):
        diff = [{"target": "director", "property": "Timeline.binding:owned", "before": "absent", "after": "reference"}]
        planned = {"exactDiff": diff, "mutationPaths": ["Assets/ArtistAuthorityFixture.unity"]}
        applied = {**planned, "verified": True, "savePerformed": False, "evidence": ["mutation_evidence", "timeline_evidence", "save_not_performed"]}
        runner.verify_apply(planned, applied, "binding")
        for patch in ({"verified": False}, {"savePerformed": True}, {"exactDiff": []}, {"mutationPaths": ["Assets/Other.unity"]}, {"evidence": []}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                runner.verify_apply(planned, {**applied, **patch}, "binding")

    def test_noop_is_not_successful_mutation(self):
        payload = {"exactDiff": [{"before": "same", "after": "same"}], "mutationPaths": ["Assets/ArtistAuthorityFixture.unity"]}
        with self.assertRaises(ValueError):
            runner.verify_apply(payload, {**payload, "verified": True, "savePerformed": False}, "binding")

    def test_observed_before_must_match_approved_after(self):
        planned = {"exactDiff": [{"target": "director", "property": "Timeline.marker:", "before": "[]", "after": "[marker]"}]}
        observed = {"exactDiff": [{"target": "director", "property": "Timeline.marker:", "before": "[marker]", "after": "[marker|marker]"}]}
        runner.verify_observed_state(planned, observed)
        with self.assertRaises(ValueError):
            runner.verify_observed_state(planned, planned)

    def test_main_uses_control_plane_approval_and_rejects_every_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / ".artist-e2e~"
            (project / "Assets").mkdir(parents=True)
            for name in (runner.SCENE, runner.TIMELINE):
                (project / name).write_text("owned", encoding="utf-8")
            output = Path(temporary) / "evidence"
            requests, plans, actual, consumed = {}, {}, {}, set()
            plane = Mock()

            def execute(_plane, _project, run, command, **kwargs):
                self.assertIsNone(command.approval_token)
                if command.operation == "apply" and kwargs["approval_ref"] in consumed:
                    raise ValueError("Artist approval has already started execution")
                if command.operation == "plan":
                    request = json.loads(command.request_json)
                    requests[run] = request
                    key = request["trackKind"] + request["trackName"]
                    after = json.dumps(request, sort_keys=True)
                    diff = {"target": "director", "property": key, "before": actual.get(key, "absent"), "after": after}
                    payload = {"exactDiff": [diff], "mutationPaths": [runner.SCENE] if request["trackKind"] == "binding" else [runner.SCENE, runner.TIMELINE]}
                    plans[run] = payload
                elif command.operation == "inspect":
                    request = requests[run]
                    kind = request["trackKind"]
                    evidence = []
                    if kind in runner.TRACK_TYPES:
                        evidence.append("timeline_track:" + runner.TRACK_TYPES[kind] + ":" + request["trackName"])
                    if kind == "binding":
                        evidence.append("binding:" + request["trackName"] + "->" + request["bindingTargetName"])
                    payload = {"evidence": evidence}
                else:
                    payload = dict(plans[run])
                    if command.operation == "apply":
                        self.assertEqual(kwargs["approval_ref"], run + "-decision")
                        consumed.add(kwargs["approval_ref"])
                        diff = payload["exactDiff"][0]
                        actual[diff["property"]] = diff["after"]
                        payload.update(verified=True, savePerformed=False, evidence=["mutation_evidence", "timeline_evidence", "save_not_performed"])
                return {"status": "completed", "durable": True, "receipt_integrity": "verified", "evidence_refs": [run + "-evidence"], "approval_plan_id": run + "-plan", "provider_result": {"status": "passed", "payload": payload}}

            def approve(_plane, _project, run, plan):
                self.assertEqual(plan, run + "-plan")
                return {"approval_decision_id": run + "-decision"}

            with patch.object(runner.sys, "argv", ["runner", str(project), str(output)]), patch.object(runner, "UnityAgentControlPlane", return_value=plane), patch.object(runner, "execute_artist", side_effect=execute), patch.object(runner, "approve_artist_execution", side_effect=approve) as approvals, patch.object(runner, "source_hashes", return_value={"source": "stable"}), patch.object(runner, "_fingerprint", return_value="fingerprint"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 0)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "PASS")
            self.assertEqual(approvals.call_count, 10)
            self.assertEqual(len(consumed), 10)
            self.assertTrue(all(item["replay_rejected"] for item in summary["cases"].values()))
            self.assertTrue((output / "shot-plan.json").is_file())
            self.assertTrue((output / "shot-plan-observe.json").is_file())
            self.assertTrue(plane.evidence_store.verify_record.called)


if __name__ == "__main__":
    unittest.main()
