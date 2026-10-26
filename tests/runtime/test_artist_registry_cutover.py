from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from tests.runtime import test_capability_resolver as fixture
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.provider_contract import load_provider_registry
from unityagent.runtime.tooling.tool_broker import ToolBroker

ROOT = Path(__file__).resolve().parents[2]


class ArtistRegistryCutoverTests(unittest.TestCase):
    setUp = fixture.CapabilityResolverTests.setUp
    snapshot = fixture.CapabilityResolverTests.snapshot
    request = fixture.CapabilityResolverTests.request

    def registry(self):
        return load_provider_registry(root=ROOT)

    def artist_facts(self):
        return {"available": True, "compatible": True, "project_bound": True, "package_installed": True, "pipeline_reachable": True, "unity_version": "6000.3.12f1", "render_pipeline": "builtin", "support_tier": "primary", "compatibility_backend": "builtin_editor_api", "package_version": "0.0.2-beta", "capabilities": ["artist.inspect"], "binding_status": "bound", "bound_instance_id": "artist-1"}

    def test_old_host_is_not_in_production_registry_and_generic_cli_still_works(self):
        registry = self.registry()
        self.assertNotIn("unity_artist_cli", registry.providers)
        result = ToolBroker(registry).resolve(self.request("scene.inspect"), self.snapshot(myunity=False, coplay=False), context=ResolutionContext(policy_allowed=True))
        self.assertEqual(result["provider_ref"], "unity_cli", result)
        self.assertNotIn("subagent_profile_id", result)
        self.assertEqual((registry.providers["unity_cli"].safety_strength, registry.providers["unity_cli"].evidence_strength), (4, 4))

    def test_artist_domain_is_gated_before_selection_and_on_fallback(self):
        broker = ToolBroker(self.registry())
        request = self.request("scene.inspect")
        request["qualifiers"] = {"domain": "visual_art"}
        for value in (None, False, "unknown"):
            snapshot = self.snapshot()
            snapshot["artist"] = None if value is None else {**self.artist_facts(), "compatible": value}
            self.assertNotEqual(broker.resolve(request, snapshot, context=ResolutionContext(policy_allowed=True))["status"], "resolved")
            self.assertNotEqual(broker.resolve_fallback(request, snapshot, context=ResolutionContext(policy_allowed=True), previous_provider_id="coplay_mcp")["status"], "resolved")
        snapshot["artist"] = self.artist_facts()
        resolved = broker.resolve(request, snapshot, context=ResolutionContext(policy_allowed=True))
        self.assertEqual(resolved["provider_ref"], "unity_cli", resolved)
        self.assertEqual(resolved["subagent_profile_id"], "artist_subagent")
        self.assertNotIn("mutation_evidence", request["required_evidence"])

    def test_domain_offer_strength_preserves_five_floor_without_raising_generic_cli(self):
        registry = self.registry()
        cli = registry.providers["unity_cli"]
        offer = cli.capabilities["domain.workflow"]
        self.assertEqual((offer.safety_strength, offer.evidence_strength), (5, 5))
        request = self.request("domain.workflow", approval_ref="approved")
        request["qualifiers"] = {"domain": "visual_art", "workflow": "camera_fov_reference"}
        snapshot = self.snapshot()
        snapshot["artist"] = self.artist_facts()
        context = ResolutionContext(policy_allowed=True, approval_complete=True)
        result = ToolBroker(registry).resolve(request, snapshot, context=context)
        self.assertEqual(result["provider_ref"], "unity_cli", result)
        weakened = replace(cli, capabilities={**cli.capabilities, "domain.workflow": replace(offer, safety_strength=4)})
        reduced_registry = replace(registry, providers={**registry.providers, "unity_cli": weakened})
        self.assertNotEqual(ToolBroker(reduced_registry).resolve(request, snapshot, context=context)["status"], "resolved")

    def test_offer_strength_unknown_is_rejected_by_registry_parser(self):
        import yaml
        from unityagent.runtime.tooling.provider_contract import REGISTRY_PATH, parse_provider_registry
        value = yaml.safe_load((ROOT / REGISTRY_PATH).read_text(encoding="utf-8"))
        for invalid in ("unknown", True, -1, 6):
            value["providers"]["unity_cli"]["capabilities"]["scene.inspect"]["safety_strength"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_provider_registry(value, root=ROOT)

    def test_removed_host_cannot_be_reintroduced_as_a_registry_entry(self):
        import copy
        import yaml
        from unityagent.runtime.tooling.provider_contract import REGISTRY_PATH, parse_provider_registry
        value = yaml.safe_load((ROOT / REGISTRY_PATH).read_text(encoding="utf-8"))
        value["providers"]["unity_artist_cli"] = copy.deepcopy(value["providers"]["unity_cli"])
        value["providers"]["unity_artist_cli"]["id"] = "unity_artist_cli"
        with self.assertRaises(ValueError):
            parse_provider_registry(value, root=ROOT)
