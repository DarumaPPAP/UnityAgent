"""Private GitHub approval / durable Stage Gate regressions (no licensed Editor simulated)."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from unityagent.cli import _fingerprint
from unityagent.control_plane.rock_import import plan_rock_import, _check_approval
from unityagent.control_plane.private_production_ci import (
    PrivateGitHubReview, STAGE_GATES, _expected, begin_stage, complete_stage,
    register_run,
)
from unityagent.persistence.state.state_store import StateStore
from unityagent.persistence.store.atomic_store import read_json


class PrivateCIContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / "project"
        self.state = self.root / "state"
        self.state.mkdir()
        for name in ("Assets", "Packages", "ProjectSettings"):
            (self.project / name).mkdir(parents=True)
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.12f1")
        (self.project / "Packages/manifest.json").write_text('{"dependencies":{}}')
        self.job_dir = self.state / "blender-jobs" / "rock-ci"
        self.job_dir.mkdir(parents=True)
        self.fbx = self.job_dir / "Rock.fbx"
        self.fbx.write_bytes(b"Kaydara FBX Binary  " + b"fixed-test-artifact" * 100)
        self.hash = hashlib.sha256(self.fbx.read_bytes()).hexdigest()
        (self.job_dir / "job.json").write_text(json.dumps({"status": "completed", "artifact_hash": self.hash}))
        (self.job_dir / "artifact.json").write_text(json.dumps({"sha256": self.hash, "uv_layers": 1}))
        self.plan = plan_rock_import(self.project, self.state, "rock-ci", _fingerprint())
        self.sha = "a" * 40
        self.run = "rock-rock-ci"
        self.manifest = register_run(store_root=self.state, plan_id=self.plan["plan_id"],
                                     run_id=self.run, source_revision=self.sha)
        self.expiry = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        self.review_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.review_state = "APPROVED"
        self.pr_head = "b" * 40
        self.document = None
        self.calls = []

        def getter(path):
            self.calls.append(path)
            if path == "":
                return {"full_name": "DarumaPPAP/UnityAgent-Private-CI", "private": True,
                        "default_branch": "main"}
            if path.startswith("/pulls/") and path.endswith("/reviews?per_page=100"):
                return [{"id": 41, "user": {"login": "reviewer"},
                         "commit_id": self.pr_head, "state": self.review_state,
                         "submitted_at": self.review_at}]
            if path.startswith("/pulls/"):
                return {"state": "open", "base": {"ref": "main"},
                        "head": {"sha": self.pr_head, "repo": {"full_name": "DarumaPPAP/UnityAgent-Private-CI"}},
                        "user": {"login": "author"}}
            if path.startswith("/collaborators/"):
                return {"permission": "write"}
            if path.startswith("/contents/"):
                return {"encoding": "base64", "type": "file",
                        "content": base64.b64encode(json.dumps(self.document).encode()).decode()}
            raise AssertionError(path)

        self.verifier = PrivateGitHubReview(repository="DarumaPPAP/UnityAgent-Private-CI",
                                            token="fixture-token", approvers={"reviewer"},
                                            get_json=getter)

    def approval(self, stage, kind, *, override=None):
        progress = read_json(StateStore(self.state).layout.run_root(self.run) / "private-ci/progress.json")
        self.document = _expected(self.manifest, progress, stage, kind)
        self.document["expires_at"] = self.expiry
        if override:
            self.document.update(override)
        return self.verifier.verify(15, _expected(self.manifest, progress, stage, kind))

    def test_private_review_binds_exact_plan_and_commit(self):
        bound = self.approval("artifact", "stage")
        self.assertEqual(bound["reviewer"], "reviewer")
        self.assertEqual(bound["head_sha"], self.pr_head)
        self.review_state = "DISMISSED"
        with self.assertRaisesRegex(ValueError, "No current"):
            self.approval("artifact", "stage")

    def test_approval_expiry_scope_and_source_are_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.approval("artifact", "stage", override={"scope_paths": []})
        with self.assertRaisesRegex(ValueError, "expired"):
            self.approval("artifact", "stage", override={"expires_at": "2020-01-01T00:00:00Z"})
        self.pr_head = "not-a-commit"
        with self.assertRaisesRegex(ValueError, "unmodified"):
            self.approval("artifact", "stage")

    def test_interruption_must_not_redispatch_or_skip_stage(self):
        self.approval("artifact", "stage")
        result = begin_stage(store_root=self.state, run_id=self.run, stage="artifact",
            checkout_revision=self.sha, workflow_run_id="902", approval_pulls={"stage": 15},
            verifier=self.verifier)
        self.assertEqual(result["state"], "running")
        with self.assertRaisesRegex(ValueError, "RECONCILIATION_REQUIRED"):
            begin_stage(store_root=self.state, run_id=self.run, stage="artifact",
                checkout_revision=self.sha, workflow_run_id="903", approval_pulls={"stage": 15},
                verifier=self.verifier)
        with self.assertRaisesRegex(ValueError, "RECONCILIATION_REQUIRED"):
            begin_stage(store_root=self.state, run_id=self.run, stage="editor",
                checkout_revision=self.sha, workflow_run_id="903",
                approval_pulls={"mutation": 15, "save": 16}, verifier=self.verifier)
        evidence = self.state / "evidence"
        evidence.mkdir()
        with self.assertRaisesRegex(ValueError, "checkout"):
            complete_stage(store_root=self.state, run_id=self.run, stage="artifact",
                checkout_revision="f"*40, workflow_run_id="902",
                evidence_directory=evidence, verifier=self.verifier)

    def _write_evidence(self, stage):
        directory = self.state / "evidence" / stage
        directory.mkdir(parents=True)
        for gate in STAGE_GATES[stage]:
            name = gate + ".raw"
            (directory / name).write_bytes(gate.encode())
            (directory / (gate + ".json")).write_text(json.dumps({
                "gate": gate, "status": "passed", "source_revision": self.sha,
                "source_sha256": self.hash, "evidence_level": "production_runtime",
                "raw_refs": {name: hashlib.sha256(gate.encode()).hexdigest()}}))
        return directory

    def test_checkpoint_and_same_logical_run_resume(self):
        self.approval("artifact", "stage")
        begin_stage(store_root=self.state, run_id=self.run, stage="artifact",
            checkout_revision=self.sha, workflow_run_id="902", approval_pulls={"stage": 15},
            verifier=self.verifier)
        directory = self._write_evidence("artifact")
        result = complete_stage(store_root=self.state, run_id=self.run, stage="artifact",
            checkout_revision=self.sha, workflow_run_id="902",
            evidence_directory=directory, verifier=self.verifier)
        self.assertEqual(result["g1_gates_observed"], 3)
        self.assertFalse(result["production_verified"])
        self.assertEqual(len(read_json(StateStore(self.state).layout.run_root(self.run) /
                                           "private-ci/progress.json")["completed"]), 1)
        self.approval("editor", "mutation")
        self.document = None
        # Each operation has an independently reviewed manifest; test it with a
        # dedicated fake verifier that resolves both fixed paths.
        original = self.verifier.verify
        def multiple(pr, expected):
            self.document = {**expected, "expires_at": self.expiry}
            return original(pr, expected)
        with patch.object(self.verifier, "verify", side_effect=multiple):
            step = begin_stage(store_root=self.state, run_id=self.run, stage="editor",
                checkout_revision=self.sha, workflow_run_id="903",
                approval_pulls={"mutation": 16, "save": 17}, verifier=self.verifier)
        self.assertEqual(set(step["approval_refs"]), {"mutation", "save"})
        with patch.dict("os.environ", {"UNITYAGENT_REQUIRE_PRIVATE_APPROVAL": "1"}):
            with patch("unityagent.control_plane.private_production_ci.verifier_from_environment",
                       return_value=self.verifier):
                self.document = {**_expected(self.manifest,
                    read_json(StateStore(self.state).layout.run_root(self.run) / "private-ci/progress.json"),
                    "editor", "mutation"), "expires_at": self.expiry}
                # Existing runtime rechecks the GitHub attestation and local scope.
                _check_approval(self.state, self.plan, step["approval_refs"]["mutation"], "mutation")

    def test_no_static_evidence_can_mark_stage_completed(self):
        self.approval("artifact", "stage")
        begin_stage(store_root=self.state, run_id=self.run, stage="artifact",
            checkout_revision=self.sha, workflow_run_id="902", approval_pulls={"stage": 15},
            verifier=self.verifier)
        directory = self._write_evidence("artifact")
        (directory / "blender_mcp.json").write_text(json.dumps({"gate": "blender_mcp", "status": "passed",
            "source_revision": self.sha, "source_sha256": self.hash,
            "evidence_level": "fixture", "raw_refs": {"blender_mcp.raw": "fake"}}))
        with self.assertRaisesRegex(ValueError, "level"):
            complete_stage(store_root=self.state, run_id=self.run, stage="artifact",
                checkout_revision=self.sha, workflow_run_id="902",
                evidence_directory=directory, verifier=self.verifier)


if __name__ == "__main__":
    unittest.main()
