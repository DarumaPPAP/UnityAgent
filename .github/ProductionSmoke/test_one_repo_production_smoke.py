from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github/ProductionSmoke/run_one_repo_smoke.py"

spec = importlib.util.spec_from_file_location("one_repo_production_smoke", MODULE_PATH)
assert spec is not None and spec.loader is not None
smoke = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = smoke
spec.loader.exec_module(smoke)


def _definition_fingerprint() -> dict[str, str]:
    return {
        "schema_version": "1.0",
        "architecture_version": "3.1",
        "policy_revision": "p",
        "prompt_revision": "q",
        "context_revision": "c",
        "graph_revision": "g",
        "runtime_profile_revision": "r",
        "tool_schema_revision": "t",
        "checkpoint_schema_revision": "cp",
        "evidence_schema_revision": "e",
        "eval_contract_revision": "v",
    }


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

    def test_artifact_index_marks_workspace_csharp_as_observed_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            case_dir = root / "case"
            workspace.mkdir()
            case_dir.mkdir()
            (workspace / "CameraDebugger.cs").write_text(
                "public sealed class CameraDebugger {}\n",
                encoding="utf-8",
            )

            smoke._artifact_index(workspace, case_dir)

            index = smoke.yaml.safe_load((case_dir / "artifact-index.yaml").read_text(encoding="utf-8"))
            self.assertEqual(index["artifacts"][0]["kind"], "observed_source")
            self.assertTrue((case_dir / index["artifacts"][0]["path"]).is_file())

    def test_envelope_keeps_conditional_unavailable_diagnostic(self):
        envelope = smoke._envelope(
            "run-1",
            "GOLDEN-ARCH-001",
            {"tool_identity": {}, "definition_fingerprint": {}},
            [
                {
                    "id": "namespace_and_type_naming_review",
                    "requirement": "conditional",
                    "status": "unavailable",
                    "evidence": "Not applicable in this execution.",
                }
            ],
            "evidence-1",
            None,
        )
        self.assertEqual(envelope["status"], "completed")
        self.assertIsNone(envelope["failure_class"])

    def test_envelope_keeps_required_unavailable_blocking(self):
        envelope = smoke._envelope(
            "run-2",
            "GOLDEN-ARCH-001",
            {"tool_identity": {}, "definition_fingerprint": {}},
            [
                {
                    "id": "architecture_fit",
                    "requirement": "required",
                    "status": "unavailable",
                    "evidence": "Required gate was not observed.",
                }
            ],
            "evidence-2",
            None,
        )
        self.assertEqual(envelope["status"], "unavailable")
        self.assertIsNone(envelope["failure_class"])

    def test_deterministic_compile_capture_is_utf8_and_replacement_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            case_dir = root / "case"
            workspace.mkdir()
            case_dir.mkdir()
            (workspace / "CameraDebugger.cs").write_text(
                "public sealed class CameraDebugger {}\n",
                encoding="utf-8",
            )
            completed = mock.Mock(returncode=0, stdout="compile passed\n", stderr="")

            with (
                mock.patch.object(smoke.shutil, "which", return_value="dotnet"),
                mock.patch.object(smoke.subprocess, "run", return_value=completed) as run,
            ):
                evidence = smoke._deterministic_mutation_evidence(
                    workspace,
                    case_dir,
                    ["CameraDebugger.cs"],
                    ["CameraDebugger.cs"],
                )

            kwargs = run.call_args.kwargs
            self.assertTrue(kwargs["text"])
            self.assertEqual(kwargs["encoding"], "utf-8")
            self.assertEqual(kwargs["errors"], "replace")
            self.assertTrue((case_dir / "compile-evidence.txt").is_file())
            self.assertEqual(evidence[-1]["status"], "passed")

    def test_persist_execution_uses_persistence_safe_evidence_id(self):
        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp)
            runtime_dir = case_dir / "runtime"
            runtime_dir.mkdir()
            (runtime_dir / "execution-result.yaml").write_text("status: passed\n", encoding="utf-8")
            result = {
                "run_id": "phase9-baseline-20260830-02-golden-arch-001",
                "step_id": "production-smoke",
                "status": "passed",
                "definition_fingerprint": _definition_fingerprint(),
            }

            evidence_id = smoke._persist_execution(case_dir, result)

            expected = "phase9-baseline-20260830-02-golden-arch-001-execution-result"
            self.assertEqual(evidence_id, expected)
            self.assertNotIn(":", evidence_id)
            self.assertTrue((case_dir / "persistence/evidence/records" / f"{expected}.json").is_file())

    def test_ci_harness_is_not_an_authority_module(self):
        self.assertTrue(MODULE_PATH.as_posix().endswith(".github/ProductionSmoke/run_one_repo_smoke.py"))
        self.assertNotIn("/Runtime/", MODULE_PATH.as_posix())
        self.assertNotIn("/Operations/", MODULE_PATH.as_posix())
        self.assertNotIn("/Eval/", MODULE_PATH.as_posix())


if __name__ == "__main__":
    unittest.main()
