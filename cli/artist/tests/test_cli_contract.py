from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "cli" / "artist" / "UnityArtist.Cli.csproj"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run_cli(*arguments: str) -> tuple[int, dict]:
    completed = subprocess.run(
        ["dotnet", "run", "--project", str(PROJECT), "--no-restore", "--", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"CLI did not return JSON (exit={completed.returncode}): {completed.stdout!r} {completed.stderr!r}"
        ) from exc
    return completed.returncode, payload


class UnityArtistCliContractTests(unittest.TestCase):
    def unity6_project(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for part in ("Assets", "Packages", "ProjectSettings"):
            (root / part).mkdir()
        (root / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.0f1\n", encoding="utf-8")
        (root / "Packages/manifest.json").write_text('{"dependencies": {}}', encoding="utf-8")
        return root

    def test_version_is_machine_readable(self):
        exit_code, payload = run_cli("version", "--format", "json", "--non-interactive")
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["product"], "UnityArtistCLI")
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["data"]["version"], "0.0.2-beta")
        self.assertEqual(payload["data"]["semanticVersion"], "0.0.2-beta")

    def test_help_exposes_artist_surface_and_not_generic_crud(self):
        exit_code, payload = run_cli("help", "--format", "json", "--non-interactive")
        self.assertEqual(exit_code, 0)
        commands = set(payload["data"]["commands"])
        self.assertTrue({"inspect", "plan", "preview", "apply", "capture", "evaluate", "refine", "cinematic", "history"}.issubset(commands))
        self.assertNotIn("create-gameobject", commands)
        self.assertNotIn("get-hierarchy", commands)

    def test_help_flag_is_accepted_by_the_standalone_executable(self):
        exit_code, payload = run_cli("--help", "--format", "json", "--non-interactive")
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "help")
        self.assertEqual(payload["status"], "passed")

    def test_release_matrix_is_exactly_three_unity6_rows(self):
        exit_code, payload = run_cli("capabilities", "--format", "json", "--non-interactive")
        self.assertEqual(exit_code, 0)
        matrix = payload["data"]["releaseMatrix"]
        self.assertEqual(len(matrix), 3)
        self.assertEqual(
            {(row["unityVersion"], row["renderPipeline"]) for row in matrix},
            {
                ("Unity 6.x+", "builtin"),
                ("Unity 6.x+", "urp"),
                ("Unity 6.x+", "hdrp"),
            },
        )

    def test_2022_3_urp_is_rejected_before_mutation(self):
        project = FIXTURES / "2022.3-urp"
        exit_code, payload = run_cli(
            "install", "--project-path", str(project), "--format", "json", "--non-interactive"
        )
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["errors"][0]["code"], "UNSUPPORTED_UNITY_VERSION")

    def test_2022_3_builtin_is_rejected_before_transport(self):
        project = FIXTURES / "2022.3-builtin"
        exit_code, payload = run_cli("doctor", "--project-path", str(project), "--format", "json", "--non-interactive")
        self.assertEqual(exit_code, 3)
        self.assertIn("UNSUPPORTED_UNITY_VERSION", {item["code"] for item in payload["errors"]})

    def test_context_manifest_receipt_requires_existing_specialist_context(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for part in ("Assets", "Packages", "ProjectSettings"):
                (root / part).mkdir()
            (root / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.0f1\n", encoding="utf-8")
            (root / "Packages/manifest.json").write_text('{"dependencies": {}}', encoding="utf-8")
            receipt = root / "context.json"
            receipt.write_text(json.dumps({"materialized_context": {"context_id": "ctx-1",
                "context_fingerprint": {"value": "sha256:1"}, "specialist_context": None}}), encoding="utf-8")
            exit_code, payload = run_cli("capture", "--project-path", str(root),
                "--context-manifest-path", str(receipt), "--format", "json", "--non-interactive")
            self.assertEqual(exit_code, 3)
            self.assertEqual(payload["errors"][0]["code"], "CONTEXT_RECEIPT_INVALID")

    @unittest.skipIf(os.name == "nt", "fake Unity CLI shell fixture uses POSIX sh")
    def test_backend_reports_received_identity_after_reading_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for part in ("Assets", "Packages", "ProjectSettings"):
                (root / part).mkdir()
            (root / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.0f1\n", encoding="utf-8")
            (root / "Packages/manifest.json").write_text('{"dependencies": {}}', encoding="utf-8")
            receipt = root / "context.json"
            receipt.write_text(json.dumps({"materialized_context": {"context_id": "ctx-generated",
                "context_fingerprint": {"value": "sha256:generated"},
                "specialist_context": {"profile_id": "artist_subagent", "items": [{"type": "project_fact"}]}}}), encoding="utf-8")
            unity = root / "unity"
            unity.write_text('#!/bin/sh\nprintf \'{"success":true}\\n\'\n', encoding="utf-8")
            unity.chmod(0o755)
            with mock.patch.dict(os.environ, {"UNITY_CLI_PATH": str(unity)}):
                exit_code, payload = run_cli("capture", "--project-path", str(root),
                    "--context-manifest-path", str(receipt), "--format", "json", "--non-interactive")
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["data"]["contextReceipt"], {
                "receivedContextId": "ctx-generated", "receivedContextFingerprint": "sha256:generated"})

    def test_apply_requires_plan_approval_and_revision_before_transport(self):
        project = self.unity6_project()
        exit_code, payload = run_cli(
            "apply", "--project-path", str(project), "--format", "json", "--non-interactive"
        )
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["errors"][0]["code"], "PLAN_ID_REQUIRED")

    def test_cinematic_apply_uses_the_same_approval_gate(self):
        project = self.unity6_project()
        exit_code, payload = run_cli(
            "cinematic", "--operation", "apply", "--project-path", str(project),
            "--format", "json", "--non-interactive"
        )
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["errors"][0]["code"], "PLAN_ID_REQUIRED")

    def test_invalid_format_is_a_typed_usage_failure(self):
        exit_code, payload = run_cli("version", "--format", "xml", "--non-interactive")
        self.assertEqual(exit_code, 3)
        self.assertEqual(payload["errors"][0]["code"], "INVALID_FORMAT")


if __name__ == "__main__":
    unittest.main()
