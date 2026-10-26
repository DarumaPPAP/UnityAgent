from __future__ import annotations

import copy
import json
import threading
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand, build_artist_pipeline_command
from unityagent.runtime.tooling.providers.unity_cli.artist_result_mapper import normalize_artist_pipeline_result
from unityagent.runtime.tooling.providers.unity_cli.discovery import UnityCliSurfaceDiscovery
from unityagent.runtime.tooling.providers.unity_cli.unity_cli_provider import UnityCliProvider
from tests.runtime import test_unity_cli_provider as cli_fixture


ROOT = Path(__file__).resolve().parents[2]
BASELINE = json.loads((Path(__file__).parent / "fixtures/artist-cutover-baseline.json").read_text(encoding="utf-8"))


def typed(case):
    return ArtistCommand(case["command"], **{key[2:].replace("-", "_"): value for key, value in case["arguments"].items()})


def output(editor, project=ROOT):
    return json.dumps({"success": True, "command": "command", "errors": [], "data": {"target": {"projectPath": str(project)}, "result": json.dumps(editor)}})


class ArtistCommandAdapterTests(unittest.TestCase):
    def test_typed_commands_preserve_source_argv_without_host(self):
        for case in BASELINE["commands"]:
            command = typed(case)
            if case["command"] == "apply" or case["id"] == "cinematic-apply":
                with self.subTest(case=case["id"]), self.assertRaises(PermissionError):
                    build_artist_pipeline_command("unity", ROOT, command)
            else:
                argv = build_artist_pipeline_command("unity", ROOT, command).argv
                self.assertEqual(argv, ("unity", "command", f'artist.{case["command"]}', "--project-path", str(ROOT), *case["pipeline_arguments"], "--format", "json", "--non-interactive", "--no-banner"))
        with self.assertRaises(FrozenInstanceError):
            ArtistCommand("inspect").name = "apply"

    def test_invalid_names_operations_arguments_and_types_never_build(self):
        commands = [ArtistCommand(name) for name in ("eval", "eval_file", "shell", "save", "artist.apply", "inspect --runtime")]
        commands.extend([ArtistCommand("inspect", plan_id="plan"), ArtistCommand("inspect", approval_token="forged"), ArtistCommand("cinematic", operation="save"), ArtistCommand("preview"), ArtistCommand("plan", request_json="[]"), ArtistCommand("plan", request_json='{"x":NaN}'), ArtistCommand("plan", request_json="{broken"), ArtistCommand("preview", plan_id=True), ArtistCommand("inspect", notes="--runtime")])
        for command in commands:
            with self.subTest(command=command), self.assertRaises(ValueError):
                build_artist_pipeline_command("unity", ROOT, command)
        for key in ("runtime", "project_path", "workflow", "context_manifest_path", "intent_file", "cli_options"):
            with self.subTest(key=key), self.assertRaises(TypeError):
                ArtistCommand("inspect", **{key: "injected"})

    def test_ambiguous_json_and_flag_values_are_rejected(self):
        for value in ('{"targetName":"A","targetName":"B"}', '{"value":1e999}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_artist_pipeline_command("unity", ROOT, ArtistCommand("plan", request_json=value))
        with self.assertRaises(ValueError):
            build_artist_pipeline_command("unity", ROOT, ArtistCommand("preview", plan_id="--runtime"))


class ArtistResultMapperTests(unittest.TestCase):
    def map(self, case, *, editor=None, **kwargs):
        return normalize_artist_pipeline_result(exit_code=0, stdout=output(editor or case["editor_result"]), command=kwargs.pop("command", typed(case)), project_root=ROOT, unity_version="6000.3.12f1", render_pipeline=kwargs.pop("render_pipeline", "builtin"), **kwargs)

    def test_observed_cli_beta14_command_identity_matches_the_requested_artist_command(self):
        envelope = json.loads(output(BASELINE["commands"][0]["editor_result"]))
        for name, expected in (("command artist.inspect", "passed"), ("command artist.history", "failed"), ("command artist.inspect extra", "failed")):
            envelope["command"] = name
            result = normalize_artist_pipeline_result(exit_code=0, stdout=json.dumps(envelope), command=ArtistCommand("inspect"), project_root=ROOT, unity_version="6000.3.12f1", render_pipeline="builtin")
            self.assertEqual(result["status"], expected, result)

    def test_source_results_preserve_payload_without_inventing_mutation(self):
        for case in BASELINE["commands"]:
            if case["command"] in {"apply", "capture", "evaluate", "refine"} or case["id"] == "cinematic-apply":
                continue
            result = self.map(case)
            with self.subTest(case=case["id"]):
                self.assertEqual(result["status"], "passed", result)
                self.assertEqual(result["payload"], case["editor_result"])
                self.assertEqual(result["provider_ref"], "unity_cli")
                self.assertNotIn("mutation_evidence", result["evidence"])
                self.assertNotIn("human_visual_acceptance", result["evidence"])
                self.assertNotIn("received_context_id", result)

    def test_inner_failure_overrides_outer_success_and_preserves_error(self):
        case = BASELINE["commands"][0]
        for code, failure in (("APPROVAL_REQUIRED", "blocked_by_approval"), ("STALE_REVISION", "precondition_failed"), ("SCOPE_VIOLATION", "scope_violation")):
            editor = copy.deepcopy(case["editor_result"])
            editor.update(status="blocked", errors=[{"code": code, "message": "rejected"}])
            result = self.map(case, editor=editor)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failure_class"], failure)
            self.assertEqual(result["error_code"], code)
            self.assertEqual(result["evidence"], [])

    def test_malformed_or_incomplete_success_is_rejected(self):
        case = BASELINE["commands"][0]
        for field, value in (("status", "unknown"), ("verified", "true"), ("command", "artist.history"), ("schemaVersion", "future"), ("revision", ""), ("savePerformed", True), ("evidence", []), ("errors", [{"code": "FAILED"}]), ("exactDiff", [{"target": "unexpected"}]), ("support", {"supported": True})):
            editor = copy.deepcopy(case["editor_result"])
            editor[field] = value
            with self.subTest(field=field):
                result = self.map(case, editor=editor)
                self.assertEqual(result["status"], "failed", result)
                self.assertEqual(result["evidence"], [])
        for stdout in ("", "{broken", "[]", json.dumps({"success": True, "command": "command", "data": {}}), output(case["editor_result"], ROOT / "other")):
            result = normalize_artist_pipeline_result(exit_code=0, stdout=stdout, command=ArtistCommand("inspect"), project_root=ROOT, unity_version="6000.3.12f1", render_pipeline="builtin")
            self.assertEqual(result["status"], "failed")

    def test_plan_identity_revision_and_exact_diff_are_bound(self):
        case = BASELINE["commands"][2]
        for field, value in (("planId", "other-plan"), ("baseRevision", "old"), ("revision", "changed"), ("exactDiff", []), ("approvalRequired", False), ("evidence", ["exact_diff"])):
            editor = copy.deepcopy(case["editor_result"])
            editor[field] = value
            with self.subTest(field=field):
                self.assertEqual(self.map(case, editor=editor)["status"], "failed")

    def test_non_camera_plans_preserve_existing_lighting_and_fog_contracts(self):
        case = BASELINE["commands"][1]
        for target, property_name in (("RenderSettings", "fogDensity"), ("Key Light", "intensity"), ("Volume", "URP.ColorAdjustments.postExposure")):
            editor = copy.deepcopy(case["editor_result"])
            editor["exactDiff"] = [{"target": target, "property": property_name, "before": "0", "after": "1"}]
            editor["evidence"].remove("camera_binding")
            if property_name.startswith("URP."):
                editor["evidence"].append("urp_volume_plan")
                editor["support"]["renderPipeline"] = "urp"
            intent = {"setFog": True, "fogDensity": 1} if property_name == "fogDensity" else {"targetName": target, "setLightIntensity": True, "lightIntensity": 1} if property_name == "intensity" else {"setVolumeLookDev": True, "volumePostExposure": 1}
            with self.subTest(property=property_name):
                result = self.map(case, editor=editor, command=ArtistCommand("plan", request_json=json.dumps(intent), expected_revision="revision-before"), render_pipeline=editor["support"]["renderPipeline"])
                self.assertEqual(result["status"], "passed", result)
                self.assertNotIn("camera_binding", result["evidence"])
                self.assertNotIn("mutation_evidence", result["evidence"])

    def test_inspection_target_elements_must_match_editor_types(self):
        case = BASELINE["commands"][0]
        valid = {"kind": "camera", "name": "Main Camera", "scenePath": "", "hierarchyPath": "Main Camera", "globalObjectId": "", "fieldOfView": 60.0, "enabled": True}
        for target in (None, 42, {}, {**valid, "enabled": "false"}, {**valid, "fieldOfView": "garbage"}, {**valid, "fieldOfView": True}, {**valid, "fieldOfView": 10**400}):
            editor = copy.deepcopy(case["editor_result"])
            editor["targets"] = [target]
            with self.subTest(target=target):
                self.assertEqual(self.map(case, editor=editor)["status"], "failed")
        editor["targets"] = [valid]
        self.assertEqual(self.map(case, editor=editor)["status"], "passed")

    def test_outer_failure_and_ambiguous_editor_json_never_pass(self):
        case = BASELINE["commands"][0]
        valid = json.loads(output(case["editor_result"]))
        ambiguous = copy.deepcopy(valid)
        ambiguous["data"]["result"] = ambiguous["data"]["result"].replace('"status": "passed"', '"status": "blocked", "status": "passed"')
        nonfinite = copy.deepcopy(valid)
        nonfinite["data"]["result"] = nonfinite["data"]["result"].replace('"targets": []', '"targets": [NaN]')
        for exit_code, stdout in ((1, json.dumps(valid)), (0, json.dumps({**valid, "success": False})), (0, json.dumps(ambiguous)), (0, json.dumps(nonfinite)), (0, json.dumps(valid).replace('"success": true', '"success": false, "success": true'))):
            result = normalize_artist_pipeline_result(exit_code=exit_code, stdout=stdout, command=ArtistCommand("inspect"), project_root=ROOT, unity_version="6000.3.12f1", render_pipeline="builtin")
            with self.subTest(stdout=stdout):
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["evidence"], [])

    def test_receipt_must_be_reported_by_editor_and_match_expected_values(self):
        case = BASELINE["commands"][0]
        expected = {"expected_context_id": "ctx-generated", "expected_context_fingerprint": "sha256:generated"}
        result = self.map(case, **expected)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("received_context_id", result)
        editor = copy.deepcopy(case["editor_result"])
        editor["contextReceipt"] = {"receivedContextId": "ctx-generated", "receivedContextFingerprint": "sha256:generated"}
        result = self.map(case, editor=editor, **expected)
        self.assertEqual(result["received_context_id"], "ctx-generated")
        self.assertEqual(result["received_context_fingerprint"], "sha256:generated")
        for field in ("receivedContextId", "receivedContextFingerprint"):
            forged = copy.deepcopy(editor)
            forged["contextReceipt"][field] = "forged"
            self.assertEqual(self.map(case, editor=forged, **expected)["status"], "failed")

    def test_mutation_capture_and_human_decision_gates_cannot_be_inferred(self):
        for case in BASELINE["commands"]:
            if case["command"] in {"apply", "capture", "evaluate", "refine"} or case["id"] == "cinematic-apply":
                result = self.map(case)
                self.assertEqual(result["status"], "failed", result)
                self.assertEqual(result["evidence"], [])


class ArtistProviderBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = cli_fixture.UnityCliProviderTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.project
        self.snapshot = self.fixture.snapshot(running=True, project_bound=True)
        self.snapshot["artist"] = {"available": True, "compatible": True, "project_bound": True, "package_installed": True, "pipeline_reachable": True, "unity_version": "6000.3.12f1", "render_pipeline": "builtin", "support_tier": "primary", "compatibility_backend": "builtin_editor_api", "package_version": "test", "capabilities": ["visual_art.refine", "visual_art.capture"], "binding_status": "bound", "bound_instance_id": "fixture-editor"}
        self.request = self.fixture.request("scene.inspect")
        self.request.update(qualifiers={"domain": "visual_art", "workflow": "inspect"})
        self.calls = []
        def dispatch(request, **kwargs):
            self.calls.append(request)
            return {"status": "passed", "result": SimpleNamespace(returncode=0, stdout=output(BASELINE["commands"][0]["editor_result"], self.root))}
        self.provider = UnityCliProvider(self.root, self.snapshot, dispatch_fn=dispatch, temp_root=self.fixture.temp_root)
        self.discovery = UnityCliSurfaceDiscovery("available", str(self.fixture.cli), "1.0.0-beta.14", frozenset({"command"}), {"path": str(self.root)}, {"instances": [{"projectPath": str(self.root), "state": "ready", "version": "6000.3.12f1"}]}, True, ({"name": "artist.inspect", "runtime_only": False},))

    def run_command(self, command=None, **kwargs):
        with patch.object(self.provider, "discover", return_value=self.discovery):
            return self.provider.run_artist_read_only(self.request, command=command or ArtistCommand("inspect"), timeout_seconds=5, policy_allowed=True, **kwargs)

    def test_read_only_uses_existing_dispatch_and_is_not_advertised(self):
        result = self.run_command()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(len(self.calls), 1)
        self.assertIn("artist.inspect", self.calls[0].command)
        self.assertEqual(self.calls[0].cwd, self.root.resolve())
        with patch.object(self.provider, "discover", return_value=self.discovery):
            self.assertNotIn("domain.workflow", self.provider.available_capabilities())

    def test_apply_token_never_enables_dispatch(self):
        for command in (ArtistCommand("apply", plan_id="plan", expected_revision="revision", approval_token="nonempty-forged-token"), ArtistCommand("cinematic", operation="apply", plan_id="plan", expected_revision="revision", approval_token="approved-looking")):
            self.assertEqual(self.run_command(command)["failure_class"], "blocked_by_approval")
        self.assertEqual(self.calls, [])

    def test_workflow_policy_floor_is_not_reinterpreted_as_read_only(self):
        self.request.update(capability="domain.workflow", operation_kind="editor_mutation", required_evidence=["domain_result", "mutation_evidence"], mutation_scope={"allowed_paths": ["Assets"], "prohibited_paths": ["ProjectSettings"]}, approval_ref="forged")
        self.assertEqual(self.run_command()["failure_class"], "scope_violation")
        self.assertEqual(self.calls, [])

    def test_read_only_scope_policy_package_and_binding_fail_closed(self):
        changes = [(self.request, "project_root", str(self.root / "other")), (self.request, "operation_kind", "arbitrary_code"), (self.request, "required_evidence", ["mutation_evidence"]), (self.snapshot["project"], "root", str(self.root / "other")), (self.snapshot["unity_editor"], "project_bound", False), (self.snapshot["artist"], "package_installed", "unknown"), (self.snapshot["artist"], "compatible", False)]
        for target, key, value in changes:
            previous = target[key]
            target[key] = value
            with self.subTest(key=key):
                self.assertEqual(self.run_command()["status"], "failed")
            target[key] = previous
        with patch.object(self.provider, "discover", return_value=self.discovery):
            result = self.provider.run_artist_read_only(self.request, command=ArtistCommand("inspect"), timeout_seconds=5, policy_allowed=False)
        self.assertEqual(result["failure_class"], "blocked_by_policy")
        event = threading.Event()
        event.set()
        self.assertEqual(self.run_command(cancel_event=event)["failure_class"], "cancelled")
        self.assertEqual(self.calls, [])

    def test_catalog_runtime_only_unknown_and_wrong_editor_are_rejected(self):
        from dataclasses import replace
        original = self.discovery
        for discovery in (replace(original, command_catalog=()), replace(original, command_catalog=({"name": "artist.inspect", "runtime_only": True},)), replace(original, project_info={}), replace(original, editor_status={"instances": [{"projectPath": str(self.root / "other"), "state": "ready"}]})):
            self.discovery = discovery
            self.assertEqual(self.run_command()["status"], "failed")
        self.assertEqual(self.calls, [])

    def test_artist_discovery_failure_reports_observed_boundary_without_dispatch(self):
        from dataclasses import replace
        cases = (
            (replace(self.discovery, pipeline_reachable=False), "unavailable", "pipeline_reachable=False"),
            (replace(self.discovery, pipeline_reachable="unknown"), "not_observed", "pipeline_reachable=unknown"),
            (replace(self.discovery, project_info=None), "not_observed", "current Project info"),
        )
        for discovery, expected_class, message in cases:
            with self.subTest(message=message):
                self.discovery = discovery
                result = self.run_command()
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["failure_class"], expected_class)
                self.assertIn(message, result["reason"])
        self.assertEqual(self.calls, [])

    def test_workflow_commands_and_required_context_do_not_claim_success(self):
        for command in (ArtistCommand("plan", request_json="{}"), ArtistCommand("preview", plan_id="plan"), ArtistCommand("capture"), ArtistCommand("evaluate", capture_id="capture", decision="accepted"), ArtistCommand("refine", evaluation_id="evaluation", request_json="{}")):
            self.assertEqual(self.run_command(command)["status"], "failed")
        self.assertEqual(self.calls, [])
        result = self.run_command(expected_context_id="ctx", expected_context_fingerprint="sha256:fingerprint")
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("received_context_id", result)

    def test_dispatch_timeout_and_cancelled_remain_typed_failures(self):
        for failure, expected in (("runtime_timeout", "timeout"), ("runtime_cancelled", "cancelled")):
            with patch.object(self.provider, "dispatch_fn", return_value={"status": "failed", "failure_class": failure}):
                result = self.run_command()
                self.assertEqual(result["failure_class"], expected)
                self.assertEqual(result["evidence"], [])

    def test_invalid_timeout_is_rejected_before_transport(self):
        for timeout in (0, -1, float("nan"), float("inf"), True, 10**400):
            with self.subTest(timeout=timeout):
                result = self.provider.run_artist_read_only(self.request, command=ArtistCommand("inspect"), timeout_seconds=timeout, policy_allowed=True)
                self.assertEqual(result["status"], "failed")
        self.assertEqual(self.calls, [])

    def test_invalid_project_identity_returns_failure_instead_of_raising(self):
        from dataclasses import replace
        original = self.discovery
        for target in (self.request, self.snapshot["project"]):
            key = "project_root" if target is self.request else "root"
            previous = target[key]
            target[key] = " "
            with self.subTest(key=key):
                self.assertEqual(self.run_command()["status"], "failed")
            target[key] = previous
        for discovery in (replace(original, project_info={"path": 42, "projectPath": str(self.root)}), replace(original, editor_status={"instances": [{"projectPath": " ", "state": "ready"}]})):
            self.discovery = discovery
            self.assertEqual(self.run_command()["status"], "failed")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
