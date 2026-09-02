from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Context.Selection.capability_selector import select_capability_context
from Orchestration.Orchestrator.orchestrator import fast_path, runtime_handoff
from Orchestration.ToolRouting.capability_request_builder import build_capability_requests
from Policy.Security.capability_policy import policy_for_capability
from Runtime.Contracts.capability_contract import (
    CONTEXT_CATALOG_PATH,
    POLICY_PATH,
    REQUEST_SCHEMA_PATH,
    RESOLUTION_SCHEMA_PATH,
    ROUTING_PATH,
    TASK_ROUTES_PATH,
    validate_capability_request,
    validate_capability_resolution,
    validate_contract_foundation,
)


class CapabilityContractTests(unittest.TestCase):
    def source_patch_request(self) -> dict:
        return {
            "schema_version": "1.0",
            "capability": "source.patch",
            "project_root": "D:/Projects/MyGame/Project",
            "operation_kind": "source_mutation",
            "required_evidence": ["source_diff"],
            "mutation_scope": {
                "allowed_paths": ["Assets/Scripts"],
                "prohibited_paths": ["ProjectSettings"],
            },
            "approval_ref": None,
            "preferred_surface": "project",
        }

    def test_capability_request_positive(self):
        validate_capability_request(self.source_patch_request())

    def test_provider_field_is_rejected_by_request_schema(self):
        request = self.source_patch_request()
        request["provider"] = "unity_cli"
        with self.assertRaises(ValidationError):
            validate_capability_request(request)

    def test_unknown_capability_fails_closed(self):
        request = self.source_patch_request()
        request["capability"] = "unknown.capability"
        with self.assertRaises(ValidationError):
            validate_capability_request(request)

    def test_mutation_scope_is_required_for_mutation_request(self):
        request = self.source_patch_request()
        request["mutation_scope"] = None
        with self.assertRaises(ValidationError):
            validate_capability_request(request)

    def test_required_evidence_rejects_unknown_value(self):
        request = self.source_patch_request()
        request["required_evidence"] = ["unknown_evidence"]
        with self.assertRaises(ValidationError):
            validate_capability_request(request)

    def test_operation_kind_cannot_downgrade_capability_policy(self):
        request = self.source_patch_request()
        request["operation_kind"] = "read"
        request["mutation_scope"] = None
        with self.assertRaises(ValueError):
            validate_capability_request(request)

    def test_required_evidence_cannot_be_weaker_than_policy(self):
        request = self.source_patch_request()
        request["required_evidence"] = ["source_read"]
        with self.assertRaises(ValueError):
            validate_capability_request(request)

    def test_resolution_preserves_typed_not_observed(self):
        value = {
            "schema_version": "1.0",
            "capability": "player.observe",
            "status": "not_observed",
            "provider_ref": None,
            "observed_surface": None,
            "evidence_supported": [],
            "failure_class": "not_observed",
            "reason": "No Player Runtime provider was observed.",
        }
        validate_capability_resolution(value)

    def test_policy_attachment_is_provider_independent(self):
        policy = policy_for_capability("scene.mutate")
        self.assertEqual(policy["operation_kind"], "editor_mutation")
        self.assertEqual(policy["risk_level"], "R3")
        self.assertTrue(policy["requires_mutation_scope"])
        self.assertNotIn("provider", policy)

    def test_route_builder_emits_unresolved_provider_independent_requests(self):
        requests = build_capability_requests(
            route_id="csharp-local-fix",
            project_root="D:/Projects/MyGame/Project",
            active_conditions={"mutation_requested", "verification_requested"},
            mutation_scope={
                "allowed_paths": ["Assets/Scripts"],
                "prohibited_paths": ["ProjectSettings"],
            },
        )
        self.assertEqual(
            [request["capability"] for request in requests],
            ["source.read", "source.patch", "compile.observe"],
        )
        for request in requests:
            self.assertNotIn("provider", request)
            validate_capability_request(request)

    def test_route_builder_fails_closed_without_mutation_scope(self):
        with self.assertRaises(ValueError):
            build_capability_requests(
                route_id="shader-change",
                project_root="D:/Projects/MyGame/Project",
                active_conditions={"mutation_requested"},
            )

    def test_context_materializes_only_selected_capability_descriptions(self):
        selected = select_capability_context(["scene.inspect", "player.observe", "scene.inspect"])
        self.assertEqual(
            [item["capability"] for item in selected],
            ["scene.inspect", "player.observe"],
        )
        with self.assertRaises(ValueError):
            select_capability_context(["unknown.capability"])

    def test_authoritative_runtime_handoff_carries_unresolved_capability_requests(self):
        requests = build_capability_requests(
            route_id="csharp-local-fix",
            project_root="D:/Projects/MyGame/Project",
            active_conditions=set(),
        )
        value = fast_path(
            run_id="run",
            route_id="csharp-local-fix",
            execution_profile="personal_full_control",
            context_id="ctx",
            context_fingerprint="fp",
            simple_task=True,
            requires_semantic_replan=False,
            runtime_action_id="inspect_sources",
            capability_requests=requests,
        )
        self.assertIsNotNone(value)
        self.assertEqual(value["runtime_handoff"]["capability_contract_mode"], "authoritative")
        self.assertEqual(
            value["runtime_handoff"]["capability_requests"][0]["capability"],
            "source.read",
        )

    def test_runtime_handoff_rejects_provider_identity(self):
        request = self.source_patch_request()
        request["provider_ref"] = "unity_cli"
        with self.assertRaises(ValueError):
            runtime_handoff(
                run_id="run",
                node_id="execute",
                route_id="csharp-local-fix",
                execution_profile="personal_full_control",
                context_id="ctx",
                context_fingerprint="fp",
                task_contract_runtime_projection={},
                mutation_scope={},
                validation_requirements=[],
                capability_requests=[request],
            )

    def test_foundation_catalogs_match_existing_task_routes(self):
        self.assertEqual(validate_contract_foundation(), [])
        routing = yaml.safe_load((ROOT / ROUTING_PATH).read_text(encoding="utf-8"))
        task_routes = yaml.safe_load((ROOT / TASK_ROUTES_PATH).read_text(encoding="utf-8"))
        self.assertEqual(set(routing["routes"]), set(task_routes["routes"]))
        self.assertTrue((ROOT / "Context/Selection/tool-capability-catalog.yaml").is_file())
        self.assertFalse((ROOT / "Context/Selection/mcp-selection.yaml").exists())

    def test_orchestration_provider_product_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_root = Path(tmp)
            for relative in (
                REQUEST_SCHEMA_PATH,
                RESOLUTION_SCHEMA_PATH,
                POLICY_PATH,
                ROUTING_PATH,
                TASK_ROUTES_PATH,
                CONTEXT_CATALOG_PATH,
            ):
                target = fixture_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)

            routing_path = fixture_root / ROUTING_PATH
            routing = yaml.safe_load(routing_path.read_text(encoding="utf-8"))
            routing["routes"]["csharp-local-fix"]["capabilities"][0]["semantic_destination"] = "unity_cli"
            routing_path.write_text(
                yaml.safe_dump(routing, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            findings = validate_contract_foundation(fixture_root)
            self.assertTrue(
                any("provider product token is forbidden" in item.message for item in findings)
            )


if __name__ == "__main__":
    unittest.main()
