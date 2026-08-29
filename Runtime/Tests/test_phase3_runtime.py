from __future__ import annotations
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from Runtime.ExecutionControl.limits import ExecutionLimits, ExecutionLimitTracker, RuntimeLimitError
from Runtime.Guardrails.mutation_guard import evaluate_mutation_scope
from Runtime.Health.probes import probe_environment
from Runtime.Harnesses.task_enforcement import runtime_enforcement_from_task_contract
from Runtime.Runner.Codex import codex_runner
from Runtime.Telemetry.runtime_telemetry import runtime_event


def fingerprint() -> dict:
    return {"schema_version": "1.0", "architecture_version": "3.1", "policy_revision": "p", "prompt_revision": "q", "context_revision": "c", "graph_revision": "g", "runtime_profile_revision": "r", "tool_schema_revision": "t", "checkpoint_schema_revision": "cp", "evidence_schema_revision": "e", "eval_contract_revision": "v"}


class Phase3RuntimeTests(unittest.TestCase):
    def test_dispatch_timeout_is_typed_and_kills_process(self):
        with tempfile.TemporaryDirectory() as temp:
            result = dispatch(DispatchRequest([sys.executable, "-S", "-c", "import time; time.sleep(2)"], Path(temp), 0.1))
            self.assertEqual(result["failure_class"], "runtime_timeout")
            self.assertTrue(result["result"].timed_out)
            self.assertEqual(result["result"].remaining_processes, 0)

    def test_dispatch_cancellation_is_typed(self):
        with tempfile.TemporaryDirectory() as temp:
            event = threading.Event()
            event.set()
            result = dispatch(DispatchRequest([sys.executable, "-S", "-c", "import time; time.sleep(2)"], Path(temp), 3), cancel_event=event)
            self.assertEqual(result["failure_class"], "runtime_cancelled")

    def test_hard_limits_do_not_semantically_replan(self):
        tracker = ExecutionLimitTracker(ExecutionLimits(1, hard_retry_ceiling=0, max_turns=1))
        tracker.begin_attempt()
        with self.assertRaises(RuntimeLimitError):
            tracker.begin_attempt()

    def test_scope_escape_is_blocked_but_mutation_noop_is_not_runtime_failure(self):
        escaped = evaluate_mutation_scope(work_kind="mutation", changed_paths=["B.cs"], allowed_paths=["A.cs"])
        self.assertEqual(escaped["scope_status"], "escaped")
        noop = evaluate_mutation_scope(work_kind="mutation", changed_paths=[], allowed_paths=["A.cs"])
        self.assertEqual(noop["status"], "passed")

    def test_selected_contract_projection_does_not_select_route(self):
        projected = runtime_enforcement_from_task_contract({"id": "csharp-local-fix", "default_execution_profile": "personal_full_control", "allowed_mutations": ["source_patch"], "required_quality_gates": ["compile"]})
        self.assertEqual(projected["task_contract_id"], "csharp-local-fix")
        self.assertNotIn("route", projected)

    def test_health_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            value = probe_environment(check_id="env", run_id="run", step_id="step", workspace=temp, runtime_profile_revision="r", tool_schema_revision="t")
            schema = yaml.safe_load((ROOT / "Runtime/Contracts/health-check-result.schema.yaml").read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(value)
            self.assertEqual(value["status"], "healthy")

    def test_runtime_telemetry_matches_operations_contract(self):
        value = runtime_event(run_id="run", step_id="step", event="dispatch_started")
        schema = yaml.safe_load((ROOT / "Operations/Observability/trace-record.schema.yaml").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(value)

    def test_codex_runner_fake_cli_preserves_structured_changed_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            (workspace / "CameraDebugger.cs").write_text("old\n", encoding="utf-8")
            fake = base / "fake_codex.py"
            fake.write_text("from pathlib import Path\nimport sys\ncwd=Path(sys.argv[sys.argv.index('--cd')+1])\n(cwd/'CameraDebugger.cs').write_text('new\\n',encoding='utf-8')\nout=Path(sys.argv[sys.argv.index('--output-last-message')+1])\nout.write_text('done\\n',encoding='utf-8')\nprint('{\"type\":\"event\"}')\n", encoding="utf-8")
            request = {"schema_version": "1.0", "run_id": "run", "step_id": "step", "action_id": "action", "workspace_root": str(workspace), "prompt": "bounded fix", "execution": {"work_kind": "mutation"}, "mutation_scope": {"allowed_paths": ["CameraDebugger.cs"], "prohibited_paths": []}, "tool_identity": {"provider": "fixture", "model": "fixture-model", "model_revision": "1", "tool_manifest_hash": "fixture"}, "definition_fingerprint": fingerprint()}
            result = codex_runner.execute(request, output, command_prefix=[sys.executable, "-S", str(fake)], timeout_seconds=5, reasoning_effort="high")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["changed_paths"], {"observation_state": "observed", "paths": ["CameraDebugger.cs"]})
            metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["changed_paths"], ["CameraDebugger.cs"])

    def test_runtime_has_no_eval_or_graph_import(self):
        forbidden = ("from Eval", "import Eval", "from Orchestration", "import Orchestration", "ContinuationController")
        for path in (ROOT / "Runtime").rglob("*.py"):
            if path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{path}: {token}")


if __name__ == "__main__":
    unittest.main()
