"""観測前のActivationを、観測後のCapability適格性と混同しない。"""
import unittest

from unityagent.orchestration.routing.route_selector import resolve_specialist
from unityagent.context.selection.specialist_context import observation_items


class ReasoningActivationTests(unittest.TestCase):
    def test_activation_does_not_claim_context_selection(self):
        snapshot = {"project": {"exists": True, "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}}
        activated = resolve_specialist("rendering-incident", "graphics.diagnose", snapshot, activation_only=True)
        self.assertEqual(activated["status"], "activated")
        self.assertEqual(activated["required_observation_capabilities"], ["project.inspect", "source.read"])
        self.assertEqual(resolve_specialist("rendering-incident", "graphics.diagnose", snapshot)["reason_code"], "required_context_missing")
        snapshot["project"]["unity_version"] = "2022.3.62f1"
        self.assertEqual(resolve_specialist("rendering-incident", "graphics.diagnose", snapshot, activation_only=True)["status"], "unsupported")

    def test_observed_facts_keep_durable_provenance_and_unknown(self):
        def observation(capability, result):
            return {"payload": {"capability": capability, "result": result}, "record": {"evidence_id": capability, "environment": {}, "target": {}, "observed_evidence": []}, "revision": "sha256:" + "a" * 64}
        values = observation_items([observation("project.inspect", {"render_pipeline": "urp"}), observation("source.read", {"path": "Assets/A.shader", "content": "Shader {}"})], ["rendering"])
        projected = {item["key"]: item for item in values}
        self.assertEqual(projected["render_pipeline"]["value"], "urp")
        self.assertEqual(projected["render_pipeline"]["source"], "evidence:project.inspect")
        self.assertEqual(projected["relevant_source"]["value"], "Assets/A.shader")
        unknown = observation_items([observation("project.inspect", {"render_pipeline": "unknown"})], ["rendering"])
        self.assertNotIn("render_pipeline", {item["key"] for item in unknown})


if __name__ == "__main__":
    unittest.main()
