from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/ProductionSmoke/run_one_repo_smoke.py"

spec = importlib.util.spec_from_file_location("one_repo_production_smoke", MODULE_PATH)
assert spec is not None and spec.loader is not None
smoke = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = smoke
spec.loader.exec_module(smoke)


class OneRepoProductionSmokeTests(unittest.TestCase):
    def test_eval_implementation_maps_to_runtime_mutation(self):
        self.assertEqual(smoke._runtime_work_kind("implementation"), "mutation")
        self.assertEqual(smoke._runtime_work_kind("analysis"), "analysis")
        self.assertEqual(smoke._runtime_work_kind("verification"), "verification")

    def test_architecture_task_routes_without_expected_route_input(self):
        fingerprint = smoke._fingerprint(
            "既存 CameraDebugger に Far Clip の変更検出を追加する設計を検討してください。今回は実装しないでください。",
            "analysis",
            [],
            [],
        )
        decision = smoke.select_route(fingerprint, smoke.load_routes(smoke.ROUTES))
        self.assertEqual(decision["route_id"], "architecture-design")
        self.assertEqual(decision["profile"], "generic_planning")

    def test_compile_evidence_review_routes_to_bounded_csharp_route(self):
        fingerprint = smoke._fingerprint(
            "C# compile: PASS のEvidenceだけで確認できたことを報告してください。",
            "verification",
            [],
            [{"gate": "compile", "status": "passed", "scope": "CameraDebugger.cs"}],
        )
        decision = smoke.select_route(fingerprint, smoke.load_routes(smoke.ROUTES))
        self.assertEqual(decision["route_id"], "csharp-local-fix")
        self.assertEqual(decision["profile"], "generic_planning")

    def test_generic_fallback_is_materializable(self):
        view = smoke.materialize_context(
            "phase8-generic-planning-unit",
            "generic-planning",
            bindings={"goal": "supplied evidence only"},
            root=ROOT,
        )
        self.assertEqual(view["route_id"], "generic-planning")
        self.assertFalse(view["unresolved_bindings"])
        self.assertNotEqual(view["budget_report"]["decision"], "blocked")

    def test_runtime_prompt_contains_no_golden_answer_or_expected_route(self):
        view = smoke.materialize_context(
            "phase8-prompt-unit",
            "generic-planning",
            bindings={"goal": "bounded read-only task"},
            root=ROOT,
        )
        prompt = smoke._prompt("ユーザー向けの検証結果だけを報告してください。", view)
        self.assertNotIn("GOLDEN-", prompt)
        self.assertNotIn("expected_route", prompt)
        self.assertNotIn("required_signals", prompt)
        self.assertNotIn("forbidden_signals", prompt)

    def test_ci_harness_is_not_an_authority_module(self):
        self.assertTrue(MODULE_PATH.as_posix().endswith(".github/ProductionSmoke/run_one_repo_smoke.py"))
        self.assertNotIn("/Runtime/", MODULE_PATH.as_posix())
        self.assertNotIn("/Operations/", MODULE_PATH.as_posix())
        self.assertNotIn("/Eval/", MODULE_PATH.as_posix())


if __name__ == "__main__":
    unittest.main()
