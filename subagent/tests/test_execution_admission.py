from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


class ExecutionAdmissionTests(unittest.TestCase):
    def test_admission_separates_semantic_reasoning_from_observation_providers(self) -> None:
        admission = yaml.safe_load((ROOT / "subagent/specialist-execution-admission.yaml").read_text(encoding="utf-8"))
        rows = {row["profile_id"]: row for row in admission["specialists"]}
        self.assertEqual(set(rows), {"graphics_subagent", "qa_subagent", "world_creator_subagent"})
        self.assertEqual(rows["graphics_subagent"]["semantic_capabilities"], ["graphics.inspect", "graphics.diagnose", "graphics.validate"])
        self.assertEqual(rows["qa_subagent"]["required_observation_capabilities"], ["profiler.observe"])
        self.assertEqual(rows["world_creator_subagent"]["required_observation_capabilities"], [])
        for row in rows.values():
            self.assertEqual(row["execution_model"], "reasoning")
            self.assertTrue(row["reasoning_runtime_required"])
            self.assertFalse(row["provider_binding_required"])
            self.assertFalse(set(row["semantic_capabilities"]) & set(row["required_observation_capabilities"]))
            self.assertEqual(row["alternatives"]["provider_backed"], "rejected_no_registered_semantic_provider")
            self.assertTrue(row["receipt_semantics"])
            self.assertTrue(row["evidence_contract"])
            self.assertTrue(row["known_limitations"])

    def test_runtime_authority_is_not_an_active_undefined_blocker(self) -> None:
        text = (ROOT / "src/unityagent/runtime/reference_implementation/subagent-catalog.yaml").read_text(encoding="utf-8")
        self.assertIn("reasoning_runtime: codex_runner", text)
        self.assertNotIn("実行Authority未定義", text)
        self.assertNotIn("Planner execution authorityを先に定義", text)


if __name__ == "__main__":
    unittest.main()
