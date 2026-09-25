from __future__ import annotations

import sys
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ControlPlane.unity_agent_control_plane import UnityAgentControlPlane, validate_entry_request
from Runtime.Tooling.Environment.discovery import discover_environment
from Runtime.Tooling.Environment.environment_snapshot import UnityCliSnapshot
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.Providers.Installer.codex_plugin_installer import CommandResult
from Runtime.Tooling.Providers.Installer.installer_provider import InstallerProvider


def fingerprint() -> dict[str, str]:
    return {
        "schema_version": "1.0",
        "architecture_version": "five-layer-v1",
        "policy_revision": "policy-v1",
        "prompt_revision": "prompt-v1",
        "context_revision": "context-v1",
        "graph_revision": "graph-v1",
        "runtime_profile_revision": "runtime-v1",
        "tool_schema_revision": "tool-v1",
        "checkpoint_schema_revision": "checkpoint-v1",
        "evidence_schema_revision": "evidence-v1",
        "eval_contract_revision": "eval-v1",
    }


class ControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / f".tmp-control-plane-{uuid.uuid4().hex}"
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.project = self.root / "Project"
        (self.project / "Assets").mkdir(parents=True)
        (self.project / "Packages").mkdir()
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.3.15f1\n", encoding="utf-8"
        )
        (self.project / "Packages/manifest.json").write_text(
            '{"dependencies": {"com.unity.pipeline": "1.0.0"}}', encoding="utf-8"
        )
        self.snapshot = discover_environment(
            str(self.project),
            editor_candidates=[],
            editor_candidates_observed=True,
            editor_processes=[],
            editor_processes_observed=True,
            unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"),
            provider_instances={"myunitymcp": [], "coplay_mcp": []},
            which_fn=lambda name: "/usr/bin/git" if name == "git" else None,
        ).to_dict()

    def entry_request(self) -> dict:
        return {
            "schema_version": "2.0",
            "request_id": "inspect-1",
            "entry_point": "codex_plugin",
            "project_root": str(self.project.resolve()),
            "intent": {"kind": "project_inspection"},
        }

    def capture_request(self) -> dict:
        request = self.entry_request()
        request["intent"] = {"kind": "visual_capture", "visual_intent": "capture camera",
            "exact_scene_or_asset_scope": "Assets/Scenes/Main.unity",
            "reference_or_visual_definition": "Main Camera image"}
        return request

    def make_artist_available(self) -> None:
        self.snapshot["unity_artist_cli"].update(available=True, compatible=True, project_bound=True,
            package_installed=True, pipeline_reachable=True, version="1.0", executable_path="/bin/true",
            package_version="1.0", unity_version="6000.3.15f1", render_pipeline="builtin",
            support_tier="supported", compatibility_backend="official", capabilities=["visual.capture"],
            failure_class=None, binding_status="bound", bound_instance_id="unity-test")

    def test_execution_facade_owns_run_and_persists_evidence(self) -> None:
        plane = UnityAgentControlPlane(self.root / "state")
        result = plane.execute(
            self.entry_request(),
            environment_snapshot=self.snapshot,
            context=ResolutionContext(policy_allowed=True),
            executors={
                "file": lambda request, context, arguments: {
                    "status": "passed",
                    "failure_class": None,
                    "provider_ref": "file",
                    "evidence": ["project_fact"],
                }
            },
            definition_fingerprint=fingerprint(),
            run_id="run-control-plane-1",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["handoff"]["route_id"], "generic-planning")
        self.assertEqual(result["handoff"]["step_id"], "inspect_sources")
        self.assertEqual(result["handoff"]["execution_profile"], "generic_planning")
        self.assertEqual(result["handoff"]["task_contract_runtime_projection"]["id"], "generic-planning")
        self.assertIn("project_fact", result["handoff"]["validation_requirements"])
        self.assertEqual(result["handoff"]["mutation_scope"], {})
        self.assertEqual([item["capability"] for item in result["handoff"]["capability_requests"]], ["project.inspect"])
        proof = json.loads((plane.state_store.layout.root / result["orchestration_decision_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(proof["route_decision"]["route_id"], "generic-planning")
        self.assertEqual(proof["capability_requests"], result["handoff"]["capability_requests"])
        self.assertTrue(result["handoff"]["context_id"].startswith("ctx-"))
        self.assertTrue(result["context_manifest_ref"])
        self.assertEqual(result["layer_trace"][0:2], ["entry", "control_plane"])
        self.assertEqual(len(result["evidence_refs"]), 1)
        state = plane.state_store.load_execution_state(result["run_id"])
        self.assertEqual(state["status"], "completed")
        self.assertNotIn("loop_state_ref", result)
        evidence = plane.evidence_store.get(result["evidence_refs"][0])
        self.assertEqual(evidence["provider_ref"], "file")
        self.assertEqual(evidence["durability"], "durable")

    def test_v1_identity_cannot_execute_and_v2_cannot_supply_identity(self) -> None:
        plane = UnityAgentControlPlane(self.root / "identity-state")
        old = self.entry_request()
        old.update(schema_version="1.0", context_id="forged", context_fingerprint="forged",
            route_id="generic-planning", node_id="inspect-project", execution_profile="generic_planning",
            task_contract_runtime_projection={}, mutation_scope={}, validation_requirements=["project_fact"],
            capability_requests=[{"schema_version": "1.0", "capability": "project.inspect",
                "project_root": str(self.project.resolve()), "operation_kind": "read",
                "required_evidence": ["project_fact"], "mutation_scope": None,
                "approval_ref": None, "preferred_surface": "project"}])
        with self.assertRaisesRegex(ValueError, "migration"):
            plane.execute(old, environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True),
                          executors={}, definition_fingerprint=fingerprint())
        forged = self.entry_request()
        forged["context_id"] = "forged"
        with self.assertRaises(Exception):
            validate_entry_request(forged)

    def test_entry_cannot_select_route_capability_or_handoff_authority(self) -> None:
        for field, value in {
            "route_id": "artist-lookdev", "capability_requests": [{"capability": "scene.mutate"}],
            "node_id": "execute_change", "execution_profile": "personal_full_control",
            "task_contract_runtime_projection": {}, "mutation_scope": {"allowed_paths": ["Assets"]},
            "validation_requirements": [],
        }.items():
            with self.subTest(field=field):
                request = self.entry_request()
                request[field] = value
                with self.assertRaises(Exception):
                    validate_entry_request(request)
        for field in ("task_fingerprint", "intent", "artifact", "scope", "failure_mode",
                      "architecture_state", "mutation_target", "evidence_state", "project_access",
                      "route_id", "capability_requests", "context_id", "context_fingerprint"):
            with self.subTest(nested_field=field):
                request = self.entry_request()
                request["intent"][field] = {"artifact": "visual"} if field == "task_fingerprint" else "forged"
                with self.assertRaises(Exception):
                    validate_entry_request(request)
        for field in ("task_fingerprint", "route_id", "capability_requests", "context_id", "context_fingerprint"):
            with self.subTest(top_field=field):
                request = self.entry_request()
                request[field] = "forged"
                with self.assertRaises(Exception):
                    validate_entry_request(request)

    def test_identical_intent_resolves_same_route_and_generated_requests(self) -> None:
        plane = UnityAgentControlPlane(self.root / "repeat-state")
        request = self.entry_request()
        def file_provider(*_):
            return {"status": "passed", "provider_ref": "file", "evidence": ["project_fact"]}
        first = plane.execute(request, environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True),
            executors={"file": file_provider}, definition_fingerprint=fingerprint())
        second = plane.execute(request, environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True),
            executors={"file": file_provider}, definition_fingerprint=fingerprint())
        self.assertEqual(first["status"], second["status"])
        self.assertEqual(first["handoff"]["route_id"], second["handoff"]["route_id"])
        self.assertEqual(first["handoff"]["capability_requests"], second["handoff"]["capability_requests"])
        proofs = [json.loads((plane.state_store.layout.root / result["orchestration_decision_ref"]).read_text(encoding="utf-8"))
                  for result in (first, second)]
        self.assertEqual(proofs[0]["task_fingerprint"], proofs[1]["task_fingerprint"])
        self.assertEqual(proofs[0]["route_decision"], proofs[1]["route_decision"])
        self.assertEqual(proofs[0]["task_fingerprint"]["evidence_state"], "unknown")

    def test_visual_intent_projection_is_deterministic(self) -> None:
        from Orchestration.Routing.route_selector import load_routes, select_route, task_fingerprint_from_intent
        intent = self.capture_request()["intent"]
        fingerprints = [task_fingerprint_from_intent(intent, self.snapshot,
            project_root=str(self.project.resolve()), policy_allowed=True) for _ in range(2)]
        self.assertEqual(fingerprints[0], fingerprints[1])
        self.assertEqual(fingerprints[0]["evidence_state"], "not_applicable")
        catalog = load_routes(ROOT / "Orchestration/Routing/task-routes.yaml")
        routes = [select_route(item, catalog) for item in fingerprints]
        self.assertEqual(routes[0], routes[1])
        self.assertEqual(routes[0]["route_id"], "artist-lookdev")
        with self.assertRaisesRegex(ValueError, "project access"):
            task_fingerprint_from_intent(intent, self.snapshot,
                project_root=str(self.project.resolve()), policy_allowed=False)

    def test_missing_required_context_blocks_before_provider(self) -> None:
        plane = UnityAgentControlPlane(self.root / "blocked-state")
        self.make_artist_available()
        request = self.capture_request()
        del request["intent"]["visual_intent"]
        called = []
        with self.assertRaises(Exception):
            plane.execute(request, environment_snapshot=self.snapshot,
                context=ResolutionContext(policy_allowed=True), executors={"file": lambda *args: called.append(True)},
                definition_fingerprint=fingerprint())
        self.assertEqual(called, [])

    def test_unknown_and_mutation_intents_fail_before_dispatch(self) -> None:
        called = []
        for kind in ("unknown", "scene_mutation", "visual_optimization"):
            with self.subTest(kind=kind):
                request = self.entry_request()
                request["intent"] = {"kind": kind}
                with self.assertRaises(Exception):
                    UnityAgentControlPlane(self.root / "unsupported-state").execute(request,
                        environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True),
                        executors={"file": lambda *_: called.append(True)}, definition_fingerprint=fingerprint())
        self.assertEqual(called, [])

    def test_artist_capture_uses_assembled_context_and_measured_budget(self) -> None:
        self.make_artist_available()
        request = self.capture_request()
        plane = UnityAgentControlPlane(self.root / "artist-state")
        from Orchestration.Routing.route_selector import resolve_specialist
        with mock.patch("ControlPlane.unity_agent_control_plane.resolve_specialist", wraps=resolve_specialist) as selection:
            result = plane.execute(request, environment_snapshot=self.snapshot,
                context=ResolutionContext(policy_allowed=True),
                executors={"unity_artist_cli": self.artist_receipt_executor, "file": lambda *_: {"status": "passed", "provider_ref": "file",
                    "evidence": ["project_fact"]}}, definition_fingerprint=fingerprint())
        self.assertEqual(selection.call_args.args[:2], ("artist-lookdev", "visual.capture"))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["handoff"]["route_id"], "artist-lookdev")
        self.assertEqual([request["capability"] for request in result["handoff"]["capability_requests"]],
                         ["project.inspect", "visual.capture"])
        self.assertEqual(result["results"][1]["resolution"]["subagent_profile_id"], "artist_subagent")
        self.assertEqual(result["results"][1]["receipt_integrity"], "verified")
        manifest_path = plane.state_store.layout.root / result["context_manifest_ref"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["budget_report"]["decision"], "within_budget")
        self.assertEqual(manifest["budget_report"]["missing_observations"], [])
        self.assertEqual(manifest["materialized_context"]["specialist_context"]["profile_id"], "artist_subagent")
        self.assertEqual(result["handoff"]["context_id"], manifest["materialized_context"]["context_id"])
        self.assertEqual(result["handoff"]["context_fingerprint"],
                         manifest["materialized_context"]["context_fingerprint"]["value"])
        proof = json.loads((plane.state_store.layout.root / result["orchestration_decision_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(proof["active_conditions"], ["visual_evidence_needed"])
        self.assertEqual(proof["context_manifest_ref"], result["context_manifest_ref"])

    @staticmethod
    def artist_receipt_executor(request, context, arguments):
        manifest = json.loads(Path(arguments["specialist_context_manifest_path"]).read_text(encoding="utf-8"))
        view = manifest["materialized_context"]
        execution_context = arguments["specialist_execution_context"]
        assert execution_context["context_id"] == view["context_id"]
        assert execution_context["context_fingerprint"] == view["context_fingerprint"]["value"]
        assert execution_context["specialist_context"] == view["specialist_context"]
        return {"status": "passed", "provider_ref": "unity_artist_cli", "evidence": ["visual_capture"],
            "received_context_id": view["context_id"],
            "received_context_fingerprint": view["context_fingerprint"]["value"]}

    def test_specialist_receipt_missing_or_mismatched_fails_closed(self) -> None:
        self.make_artist_available()
        for forged in (None, "ctx-forged"):
            with self.subTest(forged=forged):
                calls = []
                def artist(request, context, arguments):
                    calls.append(arguments)
                    result = self.artist_receipt_executor(request, context, arguments)
                    if forged is None:
                        del result["received_context_id"]
                    else:
                        result["received_context_id"] = forged
                    return result
                plane = UnityAgentControlPlane(self.root / f"receipt-{forged}")
                result = plane.execute(self.capture_request(), environment_snapshot=self.snapshot,
                    context=ResolutionContext(policy_allowed=True), executors={
                        "unity_artist_cli": artist,
                        "file": lambda *_: {"status": "passed", "provider_ref": "file", "evidence": ["project_fact"]}},
                    definition_fingerprint=fingerprint())
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["results"][-1]["receipt_integrity"], "failed")
                self.assertEqual(len(calls), 1)

    def test_artist_unavailable_does_not_block_independent_core(self) -> None:
        request = self.entry_request()
        plane = UnityAgentControlPlane(self.root / "core-state")
        result = plane.execute(request, environment_snapshot=self.snapshot,
            context=ResolutionContext(policy_allowed=True),
            executors={"file": lambda *_: {"status": "passed", "provider_ref": "file",
                "evidence": ["project_fact"]}}, definition_fingerprint=fingerprint())
        self.assertEqual(self.snapshot["unity_artist_cli"]["available"], False)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"][0]["resolution"]["provider_ref"], "file")

    def test_legacy_2022_artist_support_claim_is_ineligible(self) -> None:
        from Runtime.Tooling.Environment.discovery import _artist_compatibility
        self.assertFalse(_artist_compatibility(unity_version="2022.3.22f1", render_pipeline="builtin",
            support_tier="primary", compatibility_backend="builtin_editor_api"))

    def test_changed_project_fact_blocks_before_core_dispatch(self) -> None:
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 2022.3.0f1\n", encoding="utf-8")
        called = []
        result = UnityAgentControlPlane(self.root / "stale-state").execute(
            self.entry_request(), environment_snapshot=self.snapshot,
            context=ResolutionContext(policy_allowed=True),
            executors={"file": lambda *_: called.append(True)}, definition_fingerprint=fingerprint())
        self.assertEqual(result["status"], "blocked")
        self.assertIn("differs", result["reason"])
        self.assertEqual(called, [])

    def test_project_access_cannot_be_borrowed_from_another_snapshot(self) -> None:
        request = self.entry_request()
        request["project_root"] = str(self.root / "OtherProject")
        called = []
        result = UnityAgentControlPlane(self.root / "wrong-project").execute(request,
            environment_snapshot=self.snapshot, context=ResolutionContext(policy_allowed=True),
            executors={"file": lambda *_: called.append(True)}, definition_fingerprint=fingerprint())
        self.assertEqual(result["status"], "blocked")
        self.assertIn("project access", result["reason"])
        self.assertEqual(called, [])

    def test_legacy_camera_fov_runner_stops_before_live_actions(self) -> None:
        from Tools.run_camera_fov_reference_live import LiveFailure, run_live
        with self.assertRaisesRegex(LiveFailure, "projection migration"):
            run_live(artist_root=self.root, project=self.project)

    def test_runtime_entry_rejects_semantic_loop_identity(self) -> None:
        request = self.entry_request()
        request["loop_id"] = "inspect-loop"
        with self.assertRaises(Exception):
            validate_entry_request(request)

    def test_setup_uses_registry_resolved_installer_and_evidence(self) -> None:
        (self.project / "Packages/manifest.json").write_text(
            '{"dependencies": {"com.darumappap.unity-artist": "0.0.1-beta"}}', encoding="utf-8"
        )
        installer = InstallerProvider(
            self.project,
            which_fn=lambda name: "/tools/unity.exe" if name in {"unity", "unity-artist"} else None,
            env={},
        )
        plane = UnityAgentControlPlane(self.root / "setup-state")
        result = plane.setup(
            "codex_plugin",
            {
                "schema_version": "1.0",
                "request_id": "doctor-1",
                "operation": "doctor",
                "project_root": str(self.project.resolve()),
                "products": ["official_unity_cli", "unity_artist_cli"],
                "channel": "0.0.7-beta",
                "non_interactive": True,
            },
            executors={"installer": installer.execute},
            definition_fingerprint=fingerprint(),
            run_id="run-setup-1",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["operation"], "doctor")
        self.assertEqual(len(result["evidence_refs"]), 1)
        self.assertEqual(plane.evidence_store.get(result["evidence_refs"][0])["producer"], "installer_provider")

    def test_optional_artist_unavailable_completes_doctor_and_persists_evidence(self) -> None:
        install_calls = []
        fake_codex = self.root / "codex.exe"
        fake_codex.write_text("test executable", encoding="utf-8")

        def command_runner(arguments):
            if arguments[1:] == ["--version"]:
                return CommandResult(0, "codex-cli 0.0-test\n", "")
            if arguments[1:] == ["plugin", "list", "--json"]:
                return CommandResult(0, '[{"pluginId":"unity-agent@unity-agent","version":"0.0.7-beta","installed":true,"enabled":true}]', "")
            raise AssertionError(f"unexpected command: {arguments}")

        installer = InstallerProvider(
            self.project,
            which_fn=lambda name: "/usr/bin/unity" if name == "unity" else (str(fake_codex) if name == "codex" else None),
            command_runner=command_runner,
            installer_fn=lambda plan: install_calls.append(plan) or {"status": "passed"},
            env={},
        )
        plane = UnityAgentControlPlane(self.root / "optional-artist-state")
        result = plane.setup(
            "unity_ui",
            {
                "schema_version": "1.0",
                "request_id": "doctor-optional-artist",
                "operation": "doctor",
                "project_root": str(self.project.resolve()),
                "products": [
                    "official_unity_cli",
                    "unity_artist_cli",
                    "codex_cli",
                    "unity_agent_codex_plugin",
                ],
                "channel": "0.0.7-beta",
                "non_interactive": True,
                "codex_cli_path": str(fake_codex),
            },
            executors={"installer": installer.execute},
            definition_fingerprint=fingerprint(),
            run_id="run-doctor-optional-artist",
        )

        self.assertEqual(result["status"], "completed")
        provider_result = result["outcome"]["provider_result"]
        self.assertEqual(provider_result["status"], "passed")
        entries_by_product = {entry["product"]: entry for entry in provider_result["entries"]}
        self.assertEqual(entries_by_product["unity_artist_cli"]["status"], "unavailable")
        self.assertEqual(
            entries_by_product["unity_artist_cli"]["reason"],
            "unity_artist_cli_unavailable",
        )
        product_statuses = {entry["product"]: entry["status"] for entry in provider_result["entries"]}
        self.assertEqual(product_statuses, {
            "official_unity_cli": "verified",
            "unity_artist_cli": "unavailable",
            "codex_cli": "verified",
            "unity_agent_codex_plugin": "verified",
        })
        evidence = plane.evidence_store.get(result["evidence_refs"][0])
        self.assertEqual(evidence["verification_status"], "passed")
        self.assertEqual(install_calls, [])

    def test_approved_setup_persists_install_receipt_after_evidence_id_is_known(self) -> None:
        receipt_entry = {
            "product": "unity_artist_cli",
            "status": "installed",
            "version": "0.0.1-beta",
            "location": "C:/Users/test/AppData/Local/UnityArtistCLI/Beta/unity-artist.exe",
            "source": "github:DarumaPPAP/UnitySubAgentHub@v0.0.1-beta",
            "sha256": "sha256:" + "a" * 64,
        }
        installer = InstallerProvider(
            self.project,
            installer_fn=lambda plan: {
                "schema_version": "1.0",
                "operation": "apply",
                "status": "passed",
                "project_root": str(self.project.resolve()),
                "channel": "0.0.7-beta",
                "install_receipt": {
                    "schema_version": "1.0",
                    "receipt_id": "receipt-approved",
                    "run_id": "pending",
                    "project_root": str(self.project.resolve()),
                    "channel": "0.0.7-beta",
                    "entries": [receipt_entry],
                    "verified_at": "2026-09-11T00:00:00+00:00",
                    "evidence_refs": [],
                },
            },
            env={},
        )
        plane = UnityAgentControlPlane(self.root / "receipt-state")
        result = plane.setup(
            "unity_ui",
            {
                "schema_version": "1.0",
                "request_id": "apply-1",
                "operation": "apply",
                "project_root": str(self.project.resolve()),
                "products": ["unity_artist_cli"],
                "channel": "0.0.7-beta",
                "non_interactive": True,
                "approval_ref": "approval-1",
                "expected_plan_id": "plan-approved",
            },
            executors={"installer": installer.execute},
            executor_arguments={
                "approval_complete": True,
                "approved_plan": {
                    "plan_id": "plan-approved",
                    "project_root": str(self.project.resolve()),
                    "actions": [{"product": "unity_artist_cli", "action": "install_then_verify"}],
                },
            },
            definition_fingerprint=fingerprint(),
            run_id="run-receipt-1",
        )
        self.assertEqual(result["status"], "completed")
        self.assertIsNotNone(result["receipt_ref"])
        self.assertEqual(
            plane.receipt_store.get("receipt-approved")["evidence_refs"],
            [result["evidence_refs"][0]],
        )


if __name__ == "__main__":
    unittest.main()
