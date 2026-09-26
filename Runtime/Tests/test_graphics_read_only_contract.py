from __future__ import annotations

import copy
import unittest
from pathlib import Path

import yaml

from Runtime.ReferenceImplementation.graphics_read_only import GraphicsPilotContractError, verify_graphics_read_only


class GraphicsReadOnlyContractTests(unittest.TestCase):
    def test_consumer_profile_has_no_provider_or_mutation_scope(self) -> None:
        profile_path = Path(__file__).resolve().parents[1] / "ReferenceImplementation/graphics-pilot-profile.yaml"
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        self.assertNotIn("provider_id", profile)
        self.assertNotIn("scope", profile)
        self.assertEqual(profile["provider_resolution"], "runtime_tool_broker")
        self.assertEqual(profile["capabilities"], ["graphics.inspect", "graphics.diagnose", "graphics.validate"])

    def setUp(self) -> None:
        specialist = {"profile_id": "graphics_subagent", "capability": "graphics.diagnose", "items": [{"type": "project_fact", "key": "unity_version", "value": "6000.3"}], "required_evidence": ["graphics_diagnosis"]}
        self.manifest = {"materialized_context": {"context_id": "ctx-graphics", "context_fingerprint": {"value": "sha256:fixture"}, "specialist_context": specialist}}
        self.transported = {"context_id": "ctx-graphics", "context_fingerprint": "sha256:fixture", "specialist_context": copy.deepcopy(specialist)}
        self.result = {"status": "completed", "profile_id": "graphics_subagent", "capability": "graphics.diagnose", "confirmed_facts": ["Shader source declares pass A"], "hypotheses": ["Renderer configuration excludes A"], "rejected_hypotheses": [], "required_observations": ["Editor Frame Debugger"], "proposed_diff": None, "required_approval": "none", "observed_evidence": [{"type": "graphics_diagnosis", "source_ref": "Assets/Shaders/Example.shader", "observation": "Static source review only"}], "evidence_level": "static", "known_limitations": ["Editor and Player not observed"], "received_context_id": "ctx-graphics", "received_context_fingerprint": "sha256:fixture", "runtime_evaluation": "NOT_EVALUATED_RUNTIME"}

    def test_static_fixture_receipt_is_verified_without_runtime_claim(self) -> None:
        report = verify_graphics_read_only(self.manifest, self.transported, self.result)
        self.assertEqual(report["receipt_integrity"], "verified")
        self.assertEqual(report["runtime_evaluation"], "NOT_EVALUATED_RUNTIME")

    def test_transport_and_received_mismatch_fail_closed(self) -> None:
        transported = copy.deepcopy(self.transported)
        transported["specialist_context"]["items"][0]["value"] = "unobserved"
        with self.assertRaisesRegex(GraphicsPilotContractError, "transported"):
            verify_graphics_read_only(self.manifest, transported, self.result)
        result = {**self.result, "received_context_fingerprint": "sha256:wrong"}
        with self.assertRaisesRegex(GraphicsPilotContractError, "received"):
            verify_graphics_read_only(self.manifest, self.transported, result)

    def test_runtime_claim_mutation_and_missing_evidence_fail_closed(self) -> None:
        for change in ({"evidence_level": "editor"}, {"runtime_evaluation": "VERIFIED_RUNTIME"}, {"status": "unavailable"}, {"proposed_diff": "edit shader"}, {"observed_evidence": []}):
            with self.subTest(change=change), self.assertRaises(GraphicsPilotContractError):
                verify_graphics_read_only(self.manifest, self.transported, {**self.result, **change})


if __name__ == "__main__":
    unittest.main()
