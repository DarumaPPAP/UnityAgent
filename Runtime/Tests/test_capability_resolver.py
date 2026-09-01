from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Policy.Security.capability_policy import policy_for_capability
from Runtime.Tooling.capability_resolver import ResolutionContext, resolve_capability
from Runtime.Tooling.provider_contract import load_provider_registry
from Runtime.Tooling.tool_broker import ToolBroker


class CapabilityResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project_root = str((Path(self.tmp.name) / "Project").resolve())
        project = Path(self.project_root)
        (project / "Assets").mkdir(parents=True)
        (project / "Packages").mkdir()
        (project / "ProjectSettings").mkdir()

    def snapshot(
        self,
        *,
        cli=True,
        editor=True,
        myunity=True,
        coplay=True,
        player=True,
        myunity_binding="bound",
        coplay_binding="bound",
    ) -> dict:
        return {
            "schema_version": "1.0",
            "project": {
                "root": self.project_root,
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
                "installed": editor,
                "version": "6000.3.12f1" if editor else None,
                "executable_path": "/Unity" if editor else None,
                "project_version_match": True if editor else "unknown",
                "running": editor,
                "safe_mode": False if editor else "unknown",
                "project_bound": editor,
                "binding_status": "bound" if editor else "not_running",
                "bound_instance_id": "editor-1" if editor else None,
            },
            "unity_cli": {
                "available": cli,
                "version": "1.0" if cli else None,
                "executable_path": "/unity-cli" if cli else None,
                "failure_class": None if cli else "unavailable",
            },
            "pipeline": {"installed": True, "reachable": cli},
            "myunitymcp": {
                "reachable": True if myunity or myunity_binding == "ambiguous_binding" else False,
                "available": myunity,
                "project_bound": myunity,
                "binding_status": myunity_binding if (myunity or myunity_binding == "ambiguous_binding") else "unbound",
                "bound_instance_id": "mcp-1" if myunity and myunity_binding == "bound" else None,
            },
            "coplay_mcp": {
                "reachable": True if coplay or coplay_binding == "ambiguous_binding" else False,
                "available": coplay,
                "project_bound": coplay,
                "binding_status": coplay_binding if (coplay or coplay_binding == "ambiguous_binding") else "unbound",
                "bound_instance_id": "coplay-1" if coplay and coplay_binding == "bound" else None,
            },
            "test_framework": {"available": True},
            "build": {
                "requested_target": "StandaloneWindows64",
                "requested_target_module_available": True,
            },
            "player_runtime": {
                "reachable": player,
                "instance_id": "player-1" if player else None,
            },
            "profile_hint": "FULL",
            "binding_fingerprint": "0" * 64,
        }

    def request(
        self,
        capability: str,
        *,
        preferred_surface: str | None = None,
        approval_ref: str | None = None,
    ) -> dict:
        policy = policy_for_capability(capability)
        mutation_scope = None
        if policy["requires_mutation_scope"]:
            mutation_scope = {
                "allowed_paths": ["Assets"],
                "prohibited_paths": ["ProjectSettings"],
            }
        return {
            "schema_version": "1.0",
            "capability": capability,
            "project_root": self.project_root,
            "operation_kind": policy["operation_kind"],
            "required_evidence": list(policy["minimum_required_evidence"]),
            "mutation_scope": mutation_scope,
            "approval_ref": approval_ref,
            "preferred_surface": preferred_surface,
        }

    def test_full_environment_selects_provider_per_capability_not_global_mode(self):
        broker = ToolBroker()
        context = ResolutionContext(policy_allowed=True)
        test_result = broker.resolve(
            self.request("project.test"),
            self.snapshot(),
            context=context,
        )
        scene_result = broker.resolve(
            self.request("scene.inspect"),
            self.snapshot(),
            context=context,
        )
        self.assertEqual(test_result["provider_ref"], "unity_cli")
        self.assertEqual(scene_result["provider_ref"], "myunitymcp")

    def test_cli_absence_allows_native_editor_legal_fallback(self):
        result = resolve_capability(
            self.request("project.test"),
            self.snapshot(cli=False, myunity=False, coplay=False),
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["provider_ref"], "native_unity_editor")

    def test_scene_mutation_never_falls_back_to_raw_file_or_eval(self):
        result = resolve_capability(
            self.request("scene.mutate", approval_ref="approval-1"),
            self.snapshot(cli=False, editor=False, myunity=False, coplay=False),
            context=ResolutionContext(policy_allowed=True, approval_complete=True),
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["provider_ref"])

    def test_read_only_equivalent_evidence_fallback_excludes_unhealthy_provider(self):
        result = resolve_capability(
            self.request("project.inspect"),
            self.snapshot(),
            context=ResolutionContext(
                policy_allowed=True,
                provider_health={"myunitymcp": "unhealthy"},
            ),
        )
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["provider_ref"], "file")

    def test_infrastructure_fallback_cannot_weaken_safety_or_evidence_strength(self):
        broker = ToolBroker()
        result = broker.resolve_fallback(
            self.request("scene.inspect"),
            self.snapshot(),
            context=ResolutionContext(policy_allowed=True),
            previous_provider_id="myunitymcp",
        )
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["provider_ref"])

    def test_unhealthy_provider_is_removed_before_ranking(self):
        result = resolve_capability(
            self.request("scene.inspect"),
            self.snapshot(),
            context=ResolutionContext(
                policy_allowed=True,
                provider_health={"myunitymcp": "unhealthy"},
            ),
        )
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["provider_ref"], "coplay_mcp")

    def test_multi_instance_ambiguity_fails_closed(self):
        result = resolve_capability(
            self.request("scene.inspect"),
            self.snapshot(
                cli=False,
                myunity=False,
                coplay=False,
                myunity_binding="ambiguous_binding",
            ),
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["status"], "ambiguous_binding")
        self.assertIsNone(result["provider_ref"])

    def test_required_evidence_shortfall_excludes_provider(self):
        registry = load_provider_registry()
        coplay = registry.providers["coplay_mcp"]
        offer = coplay.capabilities["scene.mutate"]
        weak_offer = replace(offer, evidence_supported=("editor_observation",))
        weak_capabilities = dict(coplay.capabilities)
        weak_capabilities["scene.mutate"] = weak_offer
        weak_coplay = replace(coplay, capabilities=weak_capabilities)
        providers = dict(registry.providers)
        providers["coplay_mcp"] = weak_coplay
        weak_registry = replace(registry, providers=providers)

        result = resolve_capability(
            self.request("scene.mutate", approval_ref="approval-1"),
            self.snapshot(cli=False, editor=False, myunity=False, coplay=True),
            context=ResolutionContext(policy_allowed=True, approval_complete=True),
            registry=weak_registry,
        )
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["provider_ref"])

    def test_policy_denial_is_distinct_from_provider_unavailability(self):
        result = resolve_capability(
            self.request("project.inspect"),
            self.snapshot(),
            context=ResolutionContext(policy_allowed=False),
        )
        self.assertEqual(result["status"], "blocked_by_policy")

    def test_high_risk_mutation_requires_completed_approval(self):
        result = resolve_capability(
            self.request("scene.mutate"),
            self.snapshot(),
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["status"], "blocked_by_approval")

    def test_preferred_surface_is_soft_and_does_not_override_capability_priority(self):
        result = resolve_capability(
            self.request("project.inspect", preferred_surface="host"),
            self.snapshot(),
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["provider_ref"], "myunitymcp")

    def test_project_root_mismatch_is_fail_closed(self):
        request = self.request("project.inspect")
        request["project_root"] = str((Path(self.tmp.name) / "OtherProject").resolve())
        result = resolve_capability(
            request,
            self.snapshot(),
            context=ResolutionContext(policy_allowed=True),
        )
        self.assertEqual(result["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
