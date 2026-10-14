"""Runtime Project Lease isolation and dispatcher conflict regressions."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from unityagent.runtime.execution_control.resource_lease import (
    RuntimeProjectLease, ProjectLeaseUnavailable, ProjectLeaseError,
)


class ResourceLeaseTests(unittest.TestCase):
    def test_exclusive_same_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "leases"
            project = Path(tmp) / "game"
            with RuntimeProjectLease(project, lease_root=storage) as lease:
                record = json.loads((lease.directory / "lease.json").read_text())
                self.assertEqual(record["token"], lease.token)
                with self.assertRaises(ProjectLeaseUnavailable):
                    with RuntimeProjectLease(project, lease_root=storage):
                        self.fail("competing owner must never execute")
            self.assertFalse(lease.directory.exists())
            with RuntimeProjectLease(project, lease_root=storage):
                pass

    def test_disjoint_worktrees_do_not_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "leases"
            with RuntimeProjectLease(Path(tmp) / "worktree_a", lease_root=storage):
                with RuntimeProjectLease(Path(tmp) / "worktree_b", lease_root=storage):
                    pass

    def test_crashed_owner_must_not_be_auto_reclaimed(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "leases"
            project = Path(tmp) / "project"
            with RuntimeProjectLease(project, lease_root=storage) as owned:
                path = owned.directory
            path.mkdir()
            (path / "lease.json").write_text('{"pid":999999,"token":"stale"}')
            with self.assertRaises(ProjectLeaseUnavailable):
                with RuntimeProjectLease(project, lease_root=storage):
                    self.fail("expired or dead owner is not sufficient to steal")

    def test_reject_relative_and_linked_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectLeaseError):
                RuntimeProjectLease("relative/project", lease_root=Path(tmp))
            link = Path(tmp) / "link"
            try:
                link.symlink_to(Path(tmp) / "real", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(ProjectLeaseError):
                with RuntimeProjectLease(Path(tmp) / "project", lease_root=link):
                    pass

    def test_mismatched_owner_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / "leases"
            project = Path(tmp) / "project"
            with self.assertRaises(ProjectLeaseError):
                with RuntimeProjectLease(project, lease_root=storage) as owned:
                    record = owned.directory / "lease.json"
                    altered = json.loads(record.read_text())
                    altered["token"] = "intruder"
                    record.write_text(json.dumps(altered))
            self.assertTrue(owned.directory.exists())

    def test_dispatcher_declares_real_runtime_lease(self):
        from unityagent.runtime.dispatcher import tool_runtime_dispatcher as dispatcher
        self.assertIn("scene.mutate", dispatcher.EDITOR_CAPABILITIES)
        self.assertIn("source_mutation", dispatcher.MUTATION_OPERATIONS)


if __name__ == "__main__":
    unittest.main()
