import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from unityagent.cli import _fingerprint
from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.persistence.store.atomic_store import PersistenceError, sha256_json
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider


class TaskDagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        for directory in ('Assets', 'Packages', 'ProjectSettings'):
            (self.project / directory).mkdir(parents=True)
        (self.project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.15f1\n')
        (self.project / 'Packages/manifest.json').write_text('{"dependencies": {}}')
        self.plane = UnityAgentControlPlane(self.root / 'state')
        self.definition = _fingerprint()
        self.snapshot = discover_environment(self.project).to_dict()
        self.provider = FileProvider(self.project)
        self.calls = []

    def execute_file(self, request, context, arguments):
        self.calls.append(request['capability'])
        return self.provider.execute(request, context, arguments)

    def task(self, name, deps=(), gates=None):
        return {'id': name, 'workspace': str(self.project), 'depends_on': list(deps),
                'goal': 'inspect project', 'write_set': [], 'resource_claims': [],
                'required_gates': gates or {'project': ['project_fact']},
                'entry_request': {'schema_version': '2.0', 'request_id': name,
                    'entry_point': 'codex_plugin', 'project_root': str(self.project),
                    'intent': {'kind': 'project_inspection'}}}

    def run_tasks(self, tasks, **kwargs):
        with patch('unityagent.runtime.guardrails.project_lease._default_lock_root', return_value=self.root / 'locks'):
            return self.plane.execute_tasks(tasks, run_id='dag-test',
                definition_fingerprint=self.definition,
                task_parameters={t['id']: {'environment_snapshot': self.snapshot,
                    'context': ResolutionContext(policy_allowed=True),
                    'executors': {'file': self.execute_file}} for t in tasks}, **kwargs)

    def test_dependencies_require_verified_evidence_and_are_durable(self):
        result = self.run_tasks([self.task('child', ['parent']), self.task('parent')])
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['execution_order'], ['parent', 'child'])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result['tasks']['parent']['gates']['project'], 'passed')
        self.assertTrue(result['checkpoint_id'])
        self.assertEqual(self.plane.state_store.load_task_state('dag-test')['status'], 'verified')

    def test_unobserved_gate_blocks_dependents_without_dispatch(self):
        result = self.run_tasks([self.task('parent', gates={'visual': ['visual_capture']}), self.task('child', ['parent'])])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['tasks']['parent']['gates']['visual'], 'not_observed')
        self.assertEqual(result['tasks']['child']['status'], 'blocked_dependency')
        self.assertEqual(len(self.calls), 1)

    def test_resume_cannot_drop_required_gate_or_change_revision(self):
        tasks = [self.task('parent', gates={'visual': ['visual_capture']})]
        self.run_tasks(tasks)
        tasks[0]['required_gates'] = {'project': ['project_fact']}
        with self.assertRaisesRegex(ValueError, 'contract'):
            self.run_tasks(tasks, resume=True)
        tasks[0]['required_gates'] = {'visual': ['visual_capture']}
        self.definition['policy_revision'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'revision'):
            self.run_tasks(tasks, resume=True)

    def test_resume_rejects_changed_project_and_does_not_replay_completed_task(self):
        tasks = [self.task('parent')]
        self.run_tasks(tasks)
        self.run_tasks(tasks, resume=True)
        self.assertEqual(len(self.calls), 1)
        (self.project / 'Assets/user.txt').write_text('manual change')
        with self.assertRaisesRegex(ValueError, 'revision'):
            self.run_tasks(tasks, resume=True)

    def test_cycles_and_wrong_workspace_fail_before_execution(self):
        with self.assertRaises(ValueError):
            self.run_tasks([self.task('a', ['b']), self.task('b', ['a'])])
        task = self.task('a')
        task['workspace'] = str(self.root)
        with self.assertRaises(ValueError):
            self.run_tasks([task])
        self.assertEqual(self.calls, [])

    def test_failure_is_not_retried_by_scheduler(self):
        self.execute_file = lambda *args: {'status': 'failed', 'failure_class': 'blocked_by_policy', 'evidence': []}
        result = self.run_tasks([self.task('a')])
        self.assertEqual(result['tasks']['a']['status'], 'blocked')
        self.assertNotEqual(result['status'], 'verified')
