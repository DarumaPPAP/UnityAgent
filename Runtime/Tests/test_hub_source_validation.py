from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from Tools import validate_catalog_import_gate as validator


ROOT = Path(__file__).resolve().parents[2]


class HubSourceValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hub = Path(self.directory.name) / "hub"
        self.hub.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Contract Test")
        self.git("config", "user.email", "contract@example.invalid")
        # 最小Producerは実Import Gateへ渡すSnapshotをGit revisionごとに保持する。
        self.payload = (ROOT / "Runtime/Tests/Fixtures/hub-artist-subagent-catalog-v3.yaml").read_bytes()
        (self.hub / "snapshot.yaml").write_bytes(self.payload)
        exporter = self.hub / "Tests/Hub/export_agent_snapshot.py"
        exporter.parent.mkdir(parents=True)
        exporter.write_text(
            "import argparse\nfrom pathlib import Path\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('--repo-root', type=Path)\n"
            "p.add_argument('--output', type=Path)\n"
            "a = p.parse_args()\n"
            "a.output.write_bytes((a.repo_root / 'snapshot.yaml').read_bytes())\n",
            encoding="utf-8",
        )
        self.git("add", ".")
        self.git("commit", "-qm", "initial snapshot")
        self.pinned = self.git("rev-parse", "HEAD").strip()
        self.lock = Path(self.directory.name) / "sources.lock.json"
        self.lock.write_text(json.dumps({"hub": {"repository": "DarumaPPAP/UnitySubAgentHub", "commit": self.pinned}}))
        self.consumer = ROOT / "Runtime/Tests/Fixtures/artist-consumer-v1.yaml"

    def git(self, *args: str) -> str:
        return subprocess.check_output(["git", "-C", str(self.hub), *args], text=True)

    def validate(self, mode: str) -> dict:
        return validator.validate_hub_source(
            self.hub, mode, lock_path=self.lock, catalog_path=self.consumer,
        )

    def test_development_and_pinned_are_distinct_immutable_sources(self) -> None:
        snapshot = yaml.safe_load(self.payload)
        snapshot["specialists"][0]["manifest"]["identity"]["version"] = "0.0.3-beta"
        (self.hub / "snapshot.yaml").write_text(yaml.safe_dump(snapshot, sort_keys=False))
        self.git("add", ".")
        self.git("commit", "-qm", "development metadata")
        head = self.git("rev-parse", "HEAD").strip()
        committed = (self.hub / "snapshot.yaml").read_bytes()
        # 作業ツリーの未Commit内容をHEAD由来の契約として記録してはいけない。
        (self.hub / "snapshot.yaml").write_text("uncommitted invalid YAML: [")
        status_before = self.git("status", "--porcelain")
        lock_before = self.lock.read_bytes()
        consumer_before = self.consumer.read_bytes()

        development = self.validate("development")
        pinned = self.validate("pinned")

        for mode, plan, commit, payload in (
            ("development", development, head, committed),
            ("pinned", pinned, self.pinned, self.payload),
        ):
            self.assertEqual(plan["status"], "no_op")
            self.assertEqual(plan["source"]["mode"], mode)
            self.assertEqual(plan["source"]["commit"], commit)
            self.assertEqual(plan["source"]["locked_commit"], self.pinned)
            self.assertIn(commit, plan["source"]["ref"])
            self.assertEqual(plan["source"]["sha256"], "sha256:" + hashlib.sha256(payload).hexdigest())
            self.assertFalse(plan["apply"]["catalog_write_performed"])
            self.assertFalse(plan["apply"]["apply_allowed"])
        self.assertEqual(self.git("status", "--porcelain"), status_before)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), head)
        self.assertEqual(self.lock.read_bytes(), lock_before)
        self.assertEqual(self.consumer.read_bytes(), consumer_before)

    def test_missing_pinned_commit_does_not_fall_back_to_head(self) -> None:
        self.lock.write_text(json.dumps({"hub": {"repository": "DarumaPPAP/UnitySubAgentHub", "commit": "0" * 40}}))
        with self.assertRaises(ValueError):
            self.validate("pinned")

    def test_mutable_lock_and_wrong_repository_are_rejected(self) -> None:
        for repository, commit in (("DarumaPPAP/UnitySubAgentHub", "main"), ("other/Hub", self.pinned)):
            with self.subTest(repository=repository, commit=commit):
                self.lock.write_text(json.dumps({"hub": {"repository": repository, "commit": commit}}))
                with self.assertRaises(ValueError):
                    self.validate("pinned")

    def test_export_failure_is_not_reported_as_compatible(self) -> None:
        (self.hub / "Tests/Hub/export_agent_snapshot.py").write_text("raise SystemExit(1)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "broken exporter")
        with self.assertRaises(ValueError):
            self.validate("development")

    def test_cli_rejects_unsupported_capability_without_catalog_write(self) -> None:
        snapshot = yaml.safe_load(self.payload)
        snapshot["specialists"][0]["manifest"]["capabilities"][0]["operations"].append("unsupported")
        (self.hub / "snapshot.yaml").write_text(yaml.safe_dump(snapshot, sort_keys=False))
        self.git("add", ".")
        self.git("commit", "-qm", "unsupported capability")
        before = (ROOT / "Runtime/ReferenceImplementation/subagent-catalog.yaml").read_bytes()
        result = subprocess.run(
            [sys.executable, str(ROOT / "Tools/validate_catalog_import_gate.py"),
             "--hub-root", str(self.hub), "--source-mode", "development"],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("capabilities" in reason for reason in report["blocking_reasons"]))
        self.assertFalse(report["apply"]["catalog_write_performed"])
        self.assertEqual((ROOT / "Runtime/ReferenceImplementation/subagent-catalog.yaml").read_bytes(), before)

    def test_cli_requires_review_even_for_valid_low_risk_catalog_change(self) -> None:
        # 旧Profile wire互換経路の合法入力でも、CIはレビュー要求を成功扱いしない。
        snapshot = yaml.safe_load((ROOT / "Runtime/ReferenceImplementation/subagent-catalog.yaml").read_bytes())
        snapshot["profiles"]["artist_subagent"]["display_name"] = "Reviewed Artist Name"
        (self.hub / "snapshot.yaml").write_text(yaml.safe_dump(snapshot, sort_keys=False))
        self.git("add", ".")
        self.git("commit", "-qm", "display name needs review")
        result = subprocess.run(
            [sys.executable, str(ROOT / "Tools/validate_catalog_import_gate.py"),
             "--hub-root", str(self.hub), "--source-mode", "development"],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "requires_pull_request")
        self.assertEqual(report["risk"], "low")
        self.assertFalse(report["apply"]["catalog_write_performed"])


if __name__ == "__main__":
    unittest.main()
