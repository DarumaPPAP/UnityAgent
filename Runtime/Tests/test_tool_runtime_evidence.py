from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.EvidenceCapture.tool_runtime_evidence import (
    attach_capability_outcome,
    normalize_provider_result,
)
from Runtime.Telemetry.runtime_telemetry import provider_capability_metrics


class ToolRuntimeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project_root = str((Path(self.tmp.name) / "Project").resolve())
        project = Path(self.project_root)
        (project / "Assets").mkdir(parents=True)
        (project / "Packages").mkdir()
        (project / "ProjectSettings").mkdir()

    def fingerprint(self):
        return {
            "schema_version": "1.0",
            "architecture_version": "arch-test",
            "policy_revision": "policy-test",
            "prompt_revision": "prompt-test",
            "context_revision": "context-test",
            "graph_revision": "graph-test",
            "runtime_profile_revision": "runtime-test",
            "tool_schema_revision": "tool-test",
            "checkpoint_schema_revision": "checkpoint-test",
            "evidence_schema_revision": "evidence-1.2",
            "eval_contract_revision": "eval-1.2",
        }

    def snapshot(self, *, profile="FULL"):
        return {
            "schema_version": "1.0",
            "project": {
                "root": self.project_root,
                "exists": True,
                "identity_status": "bound",
                "unity_version": "6000.3.15f1",
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
                "version": "6000.3.15f1",
                "executable_path": "/Unity",
                "project_version_match": True,
                "running": True,
                "safe_mode": False,
                "project_bound": True,
                "binding_status": "bound",
                "bound_instance_id": "editor-1",
            },
            "unity_cli": {
                "available": True,
                "version": "1.0.0-beta.3",
                "executable_path": "/unity",
                "failure_class": None,
            },
            "pipeline": {"installed": True, "reachable": True},
            "myunitymcp": {
                "reachable": True,
                "available": True,
                "project_bound": True,
                "binding_status": "bound",
                "bound_instance_id": "mcp-1",
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
                "requested_target": "Switch",
                "requested_target_module_available": True,
            },
            "player_runtime": {"reachable": True, "instance_id": "player-1"},
            "profile_hint": profile,
            "binding_fingerprint": "a" * 64,
        }

    def request(self, capability):
        if capability == "player.observe":
            return {
                "schema_version": "1.0",
                "capability": capability,
                "project_root": self.project_root,
                "operation_kind": "player_observe",
                "required_evidence": ["player_observation"],
                "mutation_scope": None,
                "approval_ref": None,
                "preferred_surface": "player",
            }
        if capability == "player.mutate":
            return {
                "schema_version": "1.0",
                "capability": capability,
                "project_root": self.project_root,
                "operation_kind": "player_mutate",
                "required_evidence": ["player_observation", "mutation_evidence"],
                "mutation_scope": {
                    "allowed_paths": ["Assets"],
                    "prohibited_paths": ["ProjectSettings"],
                },
                "approval_ref": "approval-1",
                "preferred_surface": "player",
            }
        if capability == "project.test":
            return {
                "schema_version": "1.0",
                "capability": capability,
                "project_root": self.project_root,
                "operation_kind": "read",
                "required_evidence": ["test_execution"],
                "mutation_scope": None,
                "approval_ref": None,
                "preferred_surface": "editor",
            }
        if capability == "scene.mutate":
            return {
                "schema_version": "1.0",
                "capability": capability,
                "project_root": self.project_root,
                "operation_kind": "editor_mutation",
                "required_evidence": ["editor_observation", "mutation_evidence"],
                "mutation_scope": {
                    "allowed_paths": ["Assets/Scenes/Test.unity"],
                    "prohibited_paths": ["ProjectSettings"],
                },
                "approval_ref": "approval-1",
                "preferred_surface": "live_editor",
            }
        raise AssertionError(capability)

    def resolution(self, capability, provider, surface):
        return {
            "schema_version": "1.0",
            "capability": capability,
            "status": "resolved",
            "provider_ref": provider,
            "observed_surface": surface,
            "evidence_supported": [],
            "failure_class": None,
            "reason": None,
        }

    def normalize(self, request, resolution, result, **kwargs):
        return normalize_provider_result(
            request,
            resolution,
            self.snapshot(),
            result,
            run_id="run-1",
            step_id="step-1",
            evidence_id=kwargs.pop("evidence_id", "evidence-1"),
            definition_fingerprint=self.fingerprint(),
            **kwargs,
        )

    def validate_runtime_contract(self, schema_id, value):
        paths = list(ROOT.glob("**/Contracts/*.schema.yaml"))
        schemas = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]
        store = {schema["$id"]: schema for schema in schemas}
        schema = store[schema_id]
        Draft202012Validator(
            schema,
            resolver=RefResolver.from_schema(schema, store=store),
        ).validate(value)

    def test_verified_player_observation_preserves_identity_strength_and_target(self):
        evidence = self.normalize(
            self.request("player.observe"),
            self.resolution("player.observe", "player_runtime", "player"),
            {
                "status": "passed",
                "failure_class": None,
                "provider_ref": "player_runtime",
                "instance_id": "player-1",
                "target_device_id": "switch-devkit-1",
                "command_id": "observe.frame",
                "evidence": ["player_observation"],
            },
            latency_ms=12.5,
        )
        self.assertEqual(evidence["completion"], "verified")
        self.assertEqual(evidence["observation_state"], "observed")
        self.assertEqual(evidence["provider_ref"], "player_runtime")
        self.assertEqual(evidence["capability"], "player.observe")
        self.assertEqual(evidence["project_root"], self.project_root)
        self.assertEqual(evidence["environment"]["profile_hint"], "FULL")
        self.assertEqual(evidence["target"]["device_id"], "switch-devkit-1")
        self.assertEqual(evidence["safety_strength"], 4)
        self.assertEqual(evidence["evidence_strength"], 4)
        self.assertEqual(evidence["durability"], "current_run")
        self.validate_runtime_contract("urn:unityagent:runtime:execution-evidence", evidence)

    def test_provider_unavailable_is_environment_blocked_not_verified(self):
        evidence = self.normalize(
            self.request("player.observe"),
            self.resolution("player.observe", "player_runtime", "player"),
            {
                "status": "failed",
                "failure_class": "unavailable",
                "provider_ref": "player_runtime",
                "reason": "device gone",
                "evidence": [],
            },
        )
        self.assertEqual(evidence["status"], "unavailable")
        self.assertEqual(evidence["completion"], "blocked_by_environment")
        self.assertEqual(evidence["observation_state"], "not_observed")

    def test_observed_test_failure_is_verified_observation_not_infrastructure(self):
        evidence = self.normalize(
            self.request("project.test"),
            self.resolution("project.test", "unity_cli", "editor"),
            {
                "status": "failed",
                "failure_class": "observed_test_failure",
                "provider_ref": "unity_cli",
                "reason": "tests failed",
                "evidence": ["test_execution"],
            },
        )
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(evidence["completion"], "verified")
        self.assertEqual(evidence["observation_state"], "observed")

    def test_partial_verified_when_provider_observes_only_subset(self):
        evidence = self.normalize(
            self.request("player.mutate"),
            self.resolution("player.mutate", "player_runtime", "player"),
            {
                "status": "passed",
                "failure_class": None,
                "provider_ref": "player_runtime",
                "evidence": ["player_observation"],
            },
        )
        self.assertEqual(evidence["completion"], "partial_verified")
        self.assertEqual(evidence["observed_evidence"], ["player_observation"])
        self.assertEqual(
            evidence["required_evidence"],
            ["mutation_evidence", "player_observation"],
        )

    def test_raw_log_text_is_not_reinterpreted_as_fact(self):
        evidence = self.normalize(
            self.request("player.observe"),
            self.resolution("player.observe", "player_runtime", "player"),
            {
                "status": "failed",
                "failure_class": "not_observed",
                "provider_ref": "player_runtime",
                "raw_log": "SUCCESS player passed all checks",
                "evidence": [],
            },
        )
        self.assertEqual(evidence["completion"], "implemented_unverified")
        self.assertEqual(evidence["observation_state"], "not_observed")
        self.assertNotIn("SUCCESS", json.dumps(evidence))

    def test_raw_reference_and_structured_provenance_are_secret_redacted(self):
        evidence = self.normalize(
            self.request("player.observe"),
            self.resolution("player.observe", "player_runtime", "player"),
            {
                "status": "passed",
                "failure_class": None,
                "provider_ref": "player_runtime",
                "evidence": ["player_observation"],
            },
            raw_refs=[
                "artifact://player/frame.json?access_token=super-secret",
            ],
            provenance_refs=["transport://qa?token=hidden"],
        )
        encoded = json.dumps(evidence)
        self.assertNotIn("super-secret", encoded)
        self.assertNotIn("hidden", encoded)
        self.assertIn("access_token=***", evidence["raw_refs"][0])

    def test_myunitymcp_mutation_preserves_approval_revision_and_exact_diff_without_token(self):
        evidence = self.normalize(
            self.request("scene.mutate"),
            self.resolution("scene.mutate", "myunitymcp", "live_editor"),
            {
                "status": "passed",
                "failure_class": None,
                "provider_ref": "myunitymcp",
                "evidence": ["editor_observation", "mutation_evidence"],
                "redacted_provenance": {
                    "instance_id": "mcp-1",
                    "session_id": "session-1",
                    "plan_id": "plan-1",
                    "expected_revision": 7,
                    "diff_digest": "sha256:deadbeef",
                    "mutation_scope_digest": "scope-provider",
                    "approval_group": "graphics.light",
                    "approval_token": "must-not-persist",
                },
            },
            mutation_provenance={"exact_diff_ref": "artifact://diff/plan-1"},
        )
        mutation = evidence["mutation_provenance"]
        self.assertEqual(mutation["approval_ref"], "approval-1")
        self.assertEqual(mutation["expected_revision"], 7)
        self.assertEqual(mutation["diff_digest"], "sha256:deadbeef")
        self.assertEqual(mutation["exact_diff_ref"], "artifact://diff/plan-1")
        self.assertEqual(mutation["plan_ref"], "plan-1")
        self.assertEqual(mutation["session_ref"], "session-1")
        self.assertIsNotNone(mutation["scope_fingerprint"])
        self.assertNotIn("must-not-persist", json.dumps(evidence))

    def test_provider_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            self.normalize(
                self.request("player.observe"),
                self.resolution("player.observe", "player_runtime", "player"),
                {
                    "status": "passed",
                    "failure_class": None,
                    "provider_ref": "unity_cli",
                    "evidence": ["player_observation"],
                },
            )

    def test_provider_cannot_emit_undeclared_evidence(self):
        with self.assertRaises(ValueError):
            self.normalize(
                self.request("player.observe"),
                self.resolution("player.observe", "player_runtime", "player"),
                {
                    "status": "passed",
                    "failure_class": None,
                    "provider_ref": "player_runtime",
                    "evidence": ["player_observation", "source_diff"],
                },
            )

    def test_attach_capability_outcome_upgrades_execution_result_without_losing_refs(self):
        evidence = self.normalize(
            self.request("player.observe"),
            self.resolution("player.observe", "player_runtime", "player"),
            {
                "status": "passed",
                "failure_class": None,
                "provider_ref": "player_runtime",
                "evidence": ["player_observation"],
            },
        )
        execution = {
            "schema_version": "1.0",
            "run_id": "run-1",
            "step_id": "step-1",
            "action_id": "action-1",
            "status": "passed",
            "started_at": None,
            "completed_at": None,
            "exit_code": 0,
            "runtime_failure": None,
            "changed_paths": {"observation_state": "not_observed", "paths": []},
            "gate_outcomes": [],
            "tool_identity": {
                "provider": "runtime",
                "model": "none",
                "model_revision": "none",
                "tool_manifest_hash": "hash",
            },
            "evidence_refs": ["existing-evidence"],
            "telemetry_refs": [],
            "definition_fingerprint": self.fingerprint(),
        }
        updated = attach_capability_outcome(execution, evidence)
        self.assertEqual(updated["schema_version"], "1.1")
        self.assertEqual(
            updated["evidence_refs"],
            ["existing-evidence", "evidence-1"],
        )
        self.assertEqual(updated["capability_outcomes"][0]["completion"], "verified")
        self.validate_runtime_contract("urn:unityagent:runtime:execution-result", updated)

    def test_provider_telemetry_is_projection_not_raw_evidence_truth(self):
        evidence = self.normalize(
            self.request("player.observe"),
            self.resolution("player.observe", "player_runtime", "player"),
            {
                "status": "passed",
                "failure_class": None,
                "provider_ref": "player_runtime",
                "evidence": ["player_observation"],
            },
            raw_refs=["artifact://safe"],
            latency_ms=4.5,
            fallback_from="unity_cli",
        )
        metrics = provider_capability_metrics(evidence)
        names = {item["metric_name"] for item in metrics}
        self.assertEqual(
            names,
            {
                "tool_runtime.provider.availability",
                "tool_runtime.provider.selection",
                "tool_runtime.provider.fallback",
                "tool_runtime.provider.failure",
                "tool_runtime.provider.latency",
            },
        )
        fallback = next(
            item for item in metrics
            if item["metric_name"] == "tool_runtime.provider.fallback"
        )
        self.assertEqual(fallback["value"], 1.0)
        encoded = json.dumps(metrics)
        self.assertNotIn("artifact://safe", encoded)


if __name__ == "__main__":
    unittest.main()
