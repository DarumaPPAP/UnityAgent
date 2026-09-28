import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from Runtime.Tests import test_graphics_production_reasoning as graphics_fixture
from Tools import unity_agent_cli


class RunCliTests(unittest.TestCase):
    setUp = graphics_fixture.GraphicsProductionReasoningTests.setUp
    def test_host_run_reaches_reasoning_boundary_through_real_file_observations(self):
        (self.project / "ProjectSettings/GraphicsSettings.asset").write_text("GraphicsSettings:\n  m_CustomRenderPipeline: {fileID: 0}\n", encoding="utf-8")
        (self.project / "ProjectSettings/QualitySettings.asset").write_text("QualitySettings:\n  m_QualitySettings:\n  - customRenderPipeline: {fileID: 0}\n", encoding="utf-8")
        entry_path = self.root / "entry.json"
        entry_path.write_text(json.dumps(self.entry), encoding="utf-8")
        args = ["unity-agent", "run", "--request", str(entry_path), "--state-root", str(self.root / "cli-state")]
        output = io.StringIO()
        with patch.object(sys, "argv", args), patch.object(unity_agent_cli, "discover_environment", return_value=self.snapshot), redirect_stdout(output):
            code = unity_agent_cli.main()
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual([item["status"] for item in result["results"][:2]], ["completed", "completed"])
        self.assertEqual(result["results"][-1]["runtime_failure"]["failure_class"], "runner_unavailable")
        self.assertEqual(len(result["evidence_refs"]), 3)
