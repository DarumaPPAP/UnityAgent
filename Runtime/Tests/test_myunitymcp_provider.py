from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.Providers.MyUnityMcp.capability_mapper import (
    ToolDescriptor,
    materialize_capability_tools,
)
from Runtime.Tooling.Providers.MyUnityMcp.instance_binding import (
    MyUnityMcpInstanceObservation,
    bind_myunitymcp_instance,
)
from Runtime.Tooling.Providers.MyUnityMcp.myunitymcp_provider import MyUnityMcpProvider
from Runtime.Tooling.Providers.MyUnityMcp.result_mapper import (
    PreparedMutationProvenance,
    normalize_tool_result,
)


class FakeMyUnityMcpTransport:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.instances = [
            MyUnityMcpInstanceObservation(
                instance_id="mcp:1",
                reachable=True,
                project_root=str(project_root),
            )
        ]
        self.tools = [
            {"name": "graphics.inspect_project", "group": "inspect"},
            {"name": "graphics.inspect_scene", "group": "inspect"},
            {"name": "graphics.validate_scene", "group": "inspect"},
            {"name": "graphics.prepare_light_plan", "group": "plan"},
            {"name": "graphics.apply_plan", "group": "mutate"},
            {"name": "profiler.inspect_environment", "group": "profiler"},
            {"name": "profiler.inspect_counters", "group": "profiler"},
            {"name": "profiler.summarize_capture", "group": "profiler"},
            {"name": "graphics.capture_evidence", "group": "capture"},
        ]
        self.revision = 7
        self.session_id = "session:1"
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.prepare_override: dict[str, Any] | None = None
        self.apply_override: dict[str, Any] | None = None

    def list_instances(self):
        return list(self.instances)

    def list_tools(self, instance_id: str):
        self.assert_instance(instance_id)
        return list(self.tools)

    def assert_instance(self, instance_id: str):
        if instance_id != "mcp:1":
            raise ConnectionError("wrong instance")

    def call_tool(
        self,
        instance_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float,
        cancel_event: threading.Event | None = None,
    ):
        self.assert_instance(instance_id)
        self.calls.append((tool_name, dict(arguments)))
        if cancel_event is not None and cancel_event.is_set():
            raise TimeoutError("cancelled fixture")
        if tool_name == "graphics.inspect_project":
            return {
                "schemaVersion": "1.1",
                "tool": tool_name,
                "sessionId": self.session_id,
                "revision": self.revision,
                "status": "SUCCESS",
                "data": {"projectPath": str(self.project_root)},
            }
        if tool_name == "graphics.prepare_light_plan":
            if self.prepare_override is not None:
                return self.prepare_override
            return {
                "schemaVersion": "1.1",
                "tool": tool_name,
                "sessionId": self.session_id,
                "revision": self.revision,
                "status": "SUCCESS",
                "data": {
                    "planId": f"{self.session_id}:mutation-plan:abc",
                    "expectedRevision": self.revision,
                    "approvalToken": "opaque-provider-token",
                    "diffDigest": "deadbeef",
                    "mutationApplied": False,
                    "savePerformed": False,
                    "bakePerformed": False,
                },
            }
        if tool_name == "graphics.apply_plan":
            if self.apply_override is not None:
                return self.apply_override
            if arguments.get("approvalToken") != "opaque-provider-token":
                return {
                    "schemaVersion": "1.1",
                    "tool": tool_name,
                    "sessionId": self.session_id,
                    "revision": self.revision,
                    "status": "INVALID_REQUEST",
                    "summary": "approval token mismatch",
                }
            self.revision += 1
            return {
                "schemaVersion": "1.1",
                "tool": tool_name,
                "sessionId": self.session_id,
                "revision": self.revision,
                "status": "SUCCESS",
                "data": {
                    "transactionId": "tx:1",
                    "savePerformed": False,
                    "bakePerformed": False,
                },
            }
        return {
            "schemaVersion": "1.1",
            "tool": tool_name,
            "sessionId": self.session_id,
            "revision": self.revision,
            "status": "SUCCESS",
            "data": {},
        }


class MyUnityMcpProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "Project"
        (self.project / "Assets").mkdir(parents=True)
        (self.project / "Packages").mkdir()
        (self.project / "ProjectSettings").mkdir()
        self.transport = FakeMyUnityMcpTransport(self.project)
        self.provider = MyUnityMcpProvider(
            self.project,
            self.snapshot(),
            self.transport,
        )

    def snapshot(self, *, safe_mode=False, binding_status="bound", project_bound=True, available=True):
        return {
            "schema_version": "1.0",
            "project": {
                "root": str(self.project.resolve()),
                "exists": True,
                "identity_status": "bound",
                "unity_version": "6000.3.12f1",
                "required_paths": {
                    "assets": True,
                    "packages": True,
                    "project_settings": True,
                },
            },
            "filesystem": {
                "readable": True,
                "writable": True,
                "writable_in_mutation_scope": True,
            },
            "git": {"available": True, "repository_bound": True},
            "unity_editor": {
                "installed": True,
                "version": "6000.3.12f1",
                "executable_path": None,
                "project_version_match": True,
                "running": True,
                "safe_mode": safe_mode,
                "project_bound": True,
                "binding_status": "bound",
                "bound_instance_id": "editor:1",
            },
            "unity_cli": {
                "available": False,
                "version": None,
                "executable_path": None,
                "failure_class": "unavailable",
            },
            "pipeline": {"installed": False, "reachable": False},
            "myunitymcp": {
                "reachable": available,
                "available": available,
                "project_bound": project_bound,
                "binding_status": binding_status,
                "bound_instance_id": "mcp:1" if project_bound else None,
            },
            "coplay_mcp": {
                "reachable": False,
                "available": False,
                "project_bound": False,
                "binding_status": "unbound",
                "bound_instance_id": None,
            },
            "test_framework": {"available": True},
            "build": {
                "requested_target": "StandaloneWindows64",
                "requested_target_module_available": True,
            },
            "player_runtime": {"reachable": False, "instance_id": None},
            "profile_hint": "MCP_ONLY",
            "binding_fingerprint": "0" * 64,
        }

    def request(self, capability: str, *, approval_ref: str | None = None, scope=None):
        operation = "editor_mutation" if capability == "scene.mutate" else "read"
        evidence = {
            "project.inspect": ["project_fact"],
            "scene.inspect": ["editor_observation"],
            "scene.mutate": ["editor_observation", "mutation_evidence"],
            "profiler.observe": ["profiler_observation"],
            "visual.capture": ["visual_capture"],
        }[capability]
        return {
            "schema_version": "1.0",
            "capability": capability,
            "project_root": str(self.project.resolve()),
            "operation_kind": operation,
            "required_evidence": evidence,
            "mutation_scope": scope,
            "approval_ref": approval_ref,
            "preferred_surface": "live_editor",
        }

    def scope(self, allowed="Assets/Scenes/Test.unity"):
        return {"allowed_paths": [allowed], "prohibited_paths": ["ProjectSettings/"]}

    def prepare(self):
        return self.provider.prepare_mutation(
            self.request("scene.inspect"),
            workflow_key="graphics.light",
            intended_mutation_scope=self.scope(),
            prepare_arguments={"directionPlanId": "direction:1"},
            policy_allowed=True,
        )

    def test_exact_project_binding_rejects_multi_instance_and_wrong_project(self):
        multi = [
            MyUnityMcpInstanceObservation("a", True, str(self.project)),
            MyUnityMcpInstanceObservation("b", True, str(self.project)),
        ]
        self.assertEqual(bind_myunitymcp_instance(str(self.project), multi).binding_status, "ambiguous_binding")
        wrong = [MyUnityMcpInstanceObservation("a", True, str(self.project.parent / "Other"))]
        self.assertEqual(bind_myunitymcp_instance(str(self.project), wrong).binding_status, "unbound")

    def test_materialization_returns_only_requested_capability_tools(self):
        discovered = [
            ToolDescriptor("graphics.inspect_project", "inspect", {"large": "schema"}),
            ToolDescriptor("graphics.inspect_scene", "inspect"),
            ToolDescriptor("graphics.validate_scene", "inspect"),
            ToolDescriptor("graphics.prepare_light_plan", "plan"),
            ToolDescriptor("graphics.apply_plan", "mutate"),
            ToolDescriptor("unrelated.tool", "other", {"huge": "schema"}),
        ]
        tools = materialize_capability_tools("project.inspect", discovered)
        self.assertEqual([tool.name for tool in tools], ["graphics.inspect_project"])

    def test_tool_group_disabled_makes_workflow_unsupported(self):
        self.transport.tools = [
            item for item in self.transport.tools if item["name"] != "graphics.apply_plan"
        ]
        result = self.prepare()
        self.assertEqual(result["failure_class"], "unsupported")
        self.assertFalse(any(name == "graphics.prepare_light_plan" for name, _ in self.transport.calls))

    def test_prepare_is_read_only_and_freezes_scope_revision_and_provider_token(self):
        result = self.prepare()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["evidence"], ["editor_observation"])
        provenance = result["provenance"]
        self.assertEqual(provenance.expected_revision, 7)
        self.assertEqual(provenance.approval_token, "opaque-provider-token")
        self.assertEqual(provenance.diff_digest, "deadbeef")
        self.assertNotIn("approval_token", result["redacted_provenance"])
        prepare_call = [args for name, args in self.transport.calls if name == "graphics.prepare_light_plan"][0]
        self.assertEqual(prepare_call["expectedRevision"], 7)

    def test_missing_prepare_approval_token_or_diff_is_not_observed(self):
        self.transport.prepare_override = {
            "schemaVersion": "1.1",
            "tool": "graphics.prepare_light_plan",
            "sessionId": "session:1",
            "revision": 7,
            "status": "SUCCESS",
            "data": {
                "planId": "p",
                "expectedRevision": 7,
                "approvalToken": "",
                "diffDigest": "",
            },
        }
        result = self.prepare()
        self.assertEqual(result["failure_class"], "not_observed")

    def test_apply_requires_unityagent_approval_before_provider_token_is_used(self):
        provenance = self.prepare()["provenance"]
        result = self.provider.apply_prepared_mutation(
            self.request("scene.mutate", approval_ref=None, scope=self.scope()),
            provenance=provenance,
            apply_arguments={},
            policy_allowed=True,
            approval_complete=False,
        )
        self.assertEqual(result["failure_class"], "blocked_by_approval")
        self.assertFalse(any(name == "graphics.apply_plan" for name, _ in self.transport.calls))

    def test_apply_preserves_opaque_provider_provenance_and_never_saves_or_bakes(self):
        provenance = self.prepare()["provenance"]
        result = self.provider.apply_prepared_mutation(
            self.request("scene.mutate", approval_ref="approval:1", scope=self.scope()),
            provenance=provenance,
            apply_arguments={},
            policy_allowed=True,
            approval_complete=True,
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["evidence"], ["editor_observation", "mutation_evidence"])
        call = [args for name, args in self.transport.calls if name == "graphics.apply_plan"][-1]
        self.assertEqual(call["planId"], provenance.plan_id)
        self.assertEqual(call["expectedRevision"], provenance.expected_revision)
        self.assertEqual(call["approvalToken"], provenance.approval_token)
        self.assertEqual(call["saveMode"], "NONE")

    def test_editor_revision_change_after_prepare_blocks_apply_before_mutation(self):
        provenance = self.prepare()["provenance"]
        self.transport.revision += 1
        result = self.provider.apply_prepared_mutation(
            self.request("scene.mutate", approval_ref="approval:1", scope=self.scope()),
            provenance=provenance,
            apply_arguments={},
            policy_allowed=True,
            approval_complete=True,
        )
        self.assertEqual(result["failure_class"], "precondition_failed")
        self.assertFalse(any(name == "graphics.apply_plan" for name, _ in self.transport.calls))

    def test_editor_session_change_after_prepare_blocks_apply(self):
        provenance = self.prepare()["provenance"]
        self.transport.session_id = "session:2"
        result = self.provider.apply_prepared_mutation(
            self.request("scene.mutate", approval_ref="approval:1", scope=self.scope()),
            provenance=provenance,
            apply_arguments={},
            policy_allowed=True,
            approval_complete=True,
        )
        self.assertEqual(result["failure_class"], "precondition_failed")

    def test_mutation_scope_cannot_expand_after_prepare(self):
        provenance = self.prepare()["provenance"]
        changed_scope = {"allowed_paths": ["Assets"], "prohibited_paths": ["ProjectSettings/"]}
        result = self.provider.apply_prepared_mutation(
            self.request("scene.mutate", approval_ref="approval:1", scope=changed_scope),
            provenance=provenance,
            apply_arguments={},
            policy_allowed=True,
            approval_complete=True,
        )
        self.assertEqual(result["failure_class"], "scope_violation")

    def test_provider_token_mismatch_and_expiry_are_provider_failures_not_fallback(self):
        provenance = self.prepare()["provenance"]
        bad = PreparedMutationProvenance(
            workflow_key=provenance.workflow_key,
            prepare_tool=provenance.prepare_tool,
            apply_tool=provenance.apply_tool,
            approval_group=provenance.approval_group,
            instance_id=provenance.instance_id,
            session_id=provenance.session_id,
            plan_id=provenance.plan_id,
            expected_revision=provenance.expected_revision,
            approval_token="wrong",
            diff_digest=provenance.diff_digest,
            mutation_scope_digest=provenance.mutation_scope_digest,
        )
        result = self.provider.apply_prepared_mutation(
            self.request("scene.mutate", approval_ref="approval:1", scope=self.scope()),
            provenance=bad,
            apply_arguments={},
            policy_allowed=True,
            approval_complete=True,
        )
        self.assertEqual(result["failure_class"], "precondition_failed")
        self.transport.apply_override = {
            "schemaVersion": "1.1",
            "tool": "graphics.apply_plan",
            "sessionId": provenance.session_id,
            "revision": provenance.expected_revision,
            "status": "SESSION_EXPIRED",
            "summary": "expired",
        }
        expired = self.provider.apply_prepared_mutation(
            self.request("scene.mutate", approval_ref="approval:1", scope=self.scope()),
            provenance=provenance,
            apply_arguments={},
            policy_allowed=True,
            approval_complete=True,
        )
        self.assertEqual(expired["failure_class"], "precondition_failed")

    def test_save_and_bake_approval_are_not_folded_into_scene_mutation(self):
        provenance = self.prepare()["provenance"]
        save_result = self.provider.apply_prepared_mutation(
            self.request("scene.mutate", approval_ref="approval:1", scope=self.scope()),
            provenance=provenance,
            apply_arguments={"saveMode": "SAVE_SCENE"},
            policy_allowed=True,
            approval_complete=True,
        )
        self.assertEqual(save_result["failure_class"], "unsupported")
        bake_result = self.provider.prepare_mutation(
            self.request("scene.inspect"),
            workflow_key="graphics.bake",
            intended_mutation_scope=self.scope(),
            prepare_arguments={},
            policy_allowed=True,
        )
        self.assertEqual(bake_result["failure_class"], "unsupported")

    def test_safe_mode_blocks_apply_but_not_read_only_prepare(self):
        provider = MyUnityMcpProvider(self.project, self.snapshot(safe_mode=True), self.transport)
        prepared = provider.prepare_mutation(
            self.request("scene.inspect"),
            workflow_key="graphics.light",
            intended_mutation_scope=self.scope(),
            prepare_arguments={"directionPlanId": "direction:1"},
            policy_allowed=True,
        )
        self.assertEqual(prepared["status"], "passed")
        result = provider.apply_prepared_mutation(
            self.request("scene.mutate", approval_ref="approval:1", scope=self.scope()),
            provenance=prepared["provenance"],
            apply_arguments={},
            policy_allowed=True,
            approval_complete=True,
        )
        self.assertEqual(result["failure_class"], "precondition_failed")

    def test_structured_status_mapping_distinguishes_unverified_unsupported_backend(self):
        for provider_status, expected in (
            ("UNVERIFIED", "not_observed"),
            ("UNSUPPORTED", "unsupported"),
            ("BACKEND_NOT_IMPLEMENTED", "backend_not_implemented"),
        ):
            result = normalize_tool_result({"status": provider_status, "summary": provider_status})
            self.assertEqual(result["failure_class"], expected)

    def test_partial_is_not_promoted_to_pass(self):
        result = normalize_tool_result({"status": "PARTIAL", "summary": "partial"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_class"], "execution_failed")

    def test_wrong_project_or_missing_provider_is_normal_unavailable(self):
        self.transport.instances = []
        provider = MyUnityMcpProvider(
            self.project,
            self.snapshot(available=False, project_bound=False, binding_status="unbound"),
            self.transport,
        )
        result = provider.run_read(
            self.request("project.inspect"),
            policy_allowed=True,
        )
        self.assertEqual(result["failure_class"], "unavailable")

    def test_raw_domain_workflow_one_shot_is_fail_closed(self):
        result = self.provider.run_domain_workflow()
        self.assertEqual(result["failure_class"], "backend_not_implemented")


if __name__ == "__main__":
    unittest.main()
