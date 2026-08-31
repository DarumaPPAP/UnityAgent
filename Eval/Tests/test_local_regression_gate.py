from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "Tools/run_regression_gate.py"
SPEC = importlib.util.spec_from_file_location("local_regression_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class LocalRegressionGateTests(unittest.TestCase):
    def test_default_runtime_identity_matches_frozen_baseline(self):
        self.assertEqual(MODULE.DEFAULT_MODEL, "gpt-5.6-luna")
        self.assertEqual(MODULE.DEFAULT_REASONING_EFFORT, "xhigh")
        self.assertEqual(MODULE.DEFAULT_TIMEOUT_SECONDS, 600.0)

    def test_local_environment_removes_openai_api_key(self):
        env, removed = MODULE._local_codex_environment(
            {"OPENAI_API_KEY": "should-not-reach-codex", "PATH": os.environ.get("PATH", "")}
        )
        self.assertTrue(removed)
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_local_environment_does_not_require_api_key_to_exist(self):
        env, removed = MODULE._local_codex_environment({"PATH": "example"})
        self.assertFalse(removed)
        self.assertEqual(env["PATH"], "example")

    def test_command_pipeline_reuses_canonical_authorities(self):
        commands = MODULE.build_commands(
            run_id="regression-local-test",
            source_revision="b" * 40,
            model="gpt-5.6-luna",
            reasoning_effort="xhigh",
            codex_version="codex-cli test",
            timeout_seconds=600.0,
            baseline=MODULE.DEFAULT_BASELINE,
        )
        self.assertEqual(
            list(commands),
            ["validate_freeze", "production_smoke", "grade", "rebaseline", "compare"],
        )
        self.assertIn(str(MODULE.SMOKE), commands["production_smoke"])
        self.assertIn(str(MODULE.GRADE), commands["grade"])
        self.assertIn(str(MODULE.REBASELINE), commands["rebaseline"])
        self.assertIn(str(MODULE.COMPARE), commands["compare"])
        self.assertIn("--require-pass", commands["compare"])
        self.assertNotIn("historical_replay.py", " ".join(sum(commands.values(), [])))

    def test_invalid_run_id_fails_closed(self):
        with self.assertRaises(MODULE.LocalRegressionGateError):
            MODULE._safe_run_id("../escape")


if __name__ == "__main__":
    unittest.main()
