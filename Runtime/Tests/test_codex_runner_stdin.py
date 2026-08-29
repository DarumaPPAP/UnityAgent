from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.ExecutionControl.process_runtime import StreamingProcessResult
from Runtime.Runner.Codex import codex_runner


def fingerprint() -> dict:
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


class CodexRunnerStdinTests(unittest.TestCase):
    def test_long_prompt_is_sent_via_stdin_not_command_line(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            long_prompt = "UnityAgent context\n" + ("x" * 50000)
            request = {
                "schema_version": "1.0",
                "run_id": "windows-long-prompt",
                "step_id": "GOLDEN-ARCH-001",
                "action_id": "analysis",
                "workspace_root": str(workspace),
                "prompt": long_prompt,
                "execution": {
                    "profile": "personal_full_control",
                    "work_kind": "analysis",
                    "mutation_authorized": False,
                },
                "mutation_scope": {"allowed_paths": [], "prohibited_paths": []},
                "tool_identity": {
                    "provider": "fixture",
                    "model": "gpt-5.6-luna",
                    "model_revision": "gpt-5.6-luna",
                    "tool_manifest_hash": "fixture",
                },
                "definition_fingerprint": fingerprint(),
            }
            captured: dict[str, object] = {}

            def fake_run(command, **kwargs):
                captured["command"] = list(command)
                captured["stdin_text"] = kwargs.get("stdin_text")
                return StreamingProcessResult(
                    returncode=0,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    cancelled=False,
                    root_pid=1,
                    process_tree_cleanup="not_required",
                    remaining_processes=0,
                    duration_seconds=0.01,
                    first_output_latency_seconds=None,
                    event_count=0,
                    last_event_timestamp=None,
                )

            with patch.object(codex_runner, "run_streaming_process", side_effect=fake_run):
                result = codex_runner.execute(
                    request,
                    output,
                    command_prefix=["codex"],
                    timeout_seconds=330,
                    reasoning_effort="xhigh",
                )

            command = captured["command"]
            self.assertEqual(result["status"], "passed")
            self.assertIsInstance(command, list)
            self.assertEqual(command[-1], "-")
            self.assertNotIn(long_prompt, command)
            self.assertEqual(captured["stdin_text"], long_prompt)
            self.assertIn('model_reasoning_effort="xhigh"', command)


if __name__ == "__main__":
    unittest.main()
