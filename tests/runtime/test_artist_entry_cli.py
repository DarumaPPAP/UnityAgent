from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from unityagent import cli


class ArtistEntryCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Project"
        for name in ("Assets", "Packages", "ProjectSettings"):
            (self.root / name).mkdir(parents=True)
        (self.root / "Packages/manifest.json").write_text('{"dependencies":{}}', encoding="utf-8")
        (self.root / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.2f1", encoding="utf-8")

    def argv(self, operation, *options):
        return ["uagent", "artist", operation, "--project-path", str(self.root), "--state-root", str(Path(self.temp.name) / "state"), "--run-id", "artist-cli-run", *options]

    def test_artist_parser_only_accepts_typed_commands_and_refuses_caller_context_or_token(self):
        with patch("sys.argv", self.argv("inspect")):
            args = cli._parse_args()
        self.assertEqual(args.command, "artist")
        self.assertEqual(args.artist_command, "inspect")
        for options in (("--context-json", "{}"), ("--approval-token", "forged")):
            with self.subTest(options=options), patch("sys.argv", self.argv("inspect", *options)), self.assertRaises(SystemExit):
                cli._parse_args()

    def test_cli_executes_only_through_control_plane_and_reports_durable_result(self):
        output = StringIO()
        with patch("sys.argv", self.argv("inspect")), patch.object(cli, "UnityAgentControlPlane", return_value=object()) as plane, patch("unityagent.control_plane.artist_execution.execute_artist", return_value={"status": "completed", "durable": True, "evidence_refs": ["evidence"]}) as execute, redirect_stdout(output):
            status = cli.main()
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(output.getvalue())["durable"])
        self.assertEqual(execute.call_args.args[3].name, "inspect")
        self.assertIs(execute.call_args.args[0], plane.return_value)

    def test_cli_approve_does_not_execute_an_artist_command(self):
        with patch("sys.argv", self.argv("approve", "--plan-id", "artist-plan-1")), patch.object(cli, "UnityAgentControlPlane", return_value=object()), patch("unityagent.control_plane.artist_execution.approve_artist_execution", return_value={"approval_decision_id": "approved"}) as approve, patch("unityagent.control_plane.artist_execution.execute_artist") as execute, redirect_stdout(StringIO()):
            status = cli.main()
        self.assertEqual(status, 0)
        self.assertEqual(approve.call_args.args[3], "artist-plan-1")
        execute.assert_not_called()
