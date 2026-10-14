"""Project排他はOS所有権を使い、別Context/別プロセスでも競合を防ぐ。"""
from pathlib import Path
import subprocess
import os
import sys
import tempfile
import unittest


class ProjectLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / 'Project'
        self.project.mkdir()
        self.locks = Path(self.temporary.name) / 'leases'

    def lease(self, project=None):
        from unityagent.runtime.guardrails.project_lease import acquire_project_lease
        return acquire_project_lease(project or self.project, owner='run-test', lock_root=self.locks)

    def test_live_owner_cannot_be_replaced(self):
        from unityagent.runtime.guardrails.project_lease import ProjectLeaseBusy
        with self.lease() as lease:
            from unityagent.runtime.tooling.environment.project_identity import canonicalize_project_root
            self.assertEqual(lease['project_identity'], canonicalize_project_root(self.project))
            with self.assertRaises(ProjectLeaseBusy):
                with self.lease():
                    self.fail('live owner was replaced')
        with self.lease():
            pass

    def test_alias_is_same_resource(self):
        from unityagent.runtime.guardrails.project_lease import ProjectLeaseBusy
        alias = self.project.parent / 'alias'
        try:
            alias.symlink_to(self.project, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        with self.lease():
            with self.assertRaises(ProjectLeaseBusy):
                with self.lease(alias):
                    self.fail('alias bypassed the lease')

    def test_exception_releases_lease(self):
        with self.assertRaisesRegex(RuntimeError, 'task failed'):
            with self.lease():
                raise RuntimeError('task failed')
        with self.lease():
            pass

    def test_independent_project_does_not_conflict(self):
        other = self.project.parent / 'Other'
        other.mkdir()
        with self.lease():
            with self.lease(other):
                pass

    def test_another_process_cannot_acquire_same_project(self):
        script = '''
import sys
from unityagent.runtime.guardrails.project_lease import acquire_project_lease, ProjectLeaseBusy
try:
    with acquire_project_lease(sys.argv[1], owner='child', lock_root=sys.argv[2]):
        print('acquired')
except ProjectLeaseBusy:
    print('busy')
'''
        def child():
            return subprocess.run([sys.executable, '-c', script, str(self.project), str(self.locks)],
                                  text=True, capture_output=True, check=True, timeout=15).stdout.strip()
        with self.lease():
            self.assertEqual(child(), 'busy')
        self.assertEqual(child(), 'acquired')

    def test_default_namespace_does_not_depend_on_process_environment(self):
        from unityagent.runtime.guardrails.project_lease import acquire_project_lease
        script = """
import sys
from unityagent.runtime.guardrails.project_lease import acquire_project_lease, ProjectLeaseBusy
try:
    with acquire_project_lease(sys.argv[1], owner='child'):
        print('acquired')
except ProjectLeaseBusy:
    print('busy')
"""
        environment = dict(os.environ, LOCALAPPDATA=str(self.project.parent / 'other-profile'),
                           HOME=str(self.project.parent / 'other-home'), PYTHONPATH=os.pathsep.join(sys.path))
        with acquire_project_lease(self.project, owner='parent'):
            child = subprocess.run([sys.executable, '-c', script, str(self.project)],
                                   env=environment, text=True, capture_output=True, timeout=15, check=True)
            self.assertEqual(child.stdout.strip(), 'busy')

    def test_unknown_project_is_rejected(self):
        with self.assertRaises((FileNotFoundError, ValueError)):
            with self.lease(self.project.parent / 'missing'):
                self.fail('unknown Project was leased')
