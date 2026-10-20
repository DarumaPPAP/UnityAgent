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

    def test_preapproved_semantic_repair_is_bounded_and_keeps_required_gates(self):
        original = self.execute_file
        attempts = []
        def repairable(request, context, arguments):
            attempts.append(request)
            if len(attempts) == 1:
                return {'status':'failed','failure_class':'execution_failed','reason':'semantic validation failed','evidence':[]}
            return original(request,context,arguments)
        self.execute_file = repairable
        task = self.task('repair')
        task['repair_candidates'] = [self.task('candidate')['entry_request']]
        task['semantic_repair_limit'] = 1
        result = self.run_tasks([task])
        self.assertEqual(result['status'],'verified',result)
        self.assertEqual(len(attempts),2)
        self.assertEqual(result['tasks']['repair']['semantic_retries'],1)
        self.assertEqual(len(result['tasks']['repair']['handoff_history']),2)

    def test_repeated_failure_and_unavailable_gate_do_not_loop(self):
        attempts = []
        def failing(*args):
            attempts.append(1)
            return {'status':'failed','failure_class':'execution_failed','reason':'same','evidence':[]}
        self.execute_file = failing
        task = self.task('repair')
        task['repair_candidates'] = [self.task('r1')['entry_request'],self.task('r2')['entry_request']]
        task['semantic_repair_limit'] = 2
        result = self.run_tasks([task])
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(len(attempts),2)


    def test_resume_does_not_duplicate_completed_observation(self):
        tasks = [self.task('parent')]
        first = self.run_tasks(tasks)
        refs = first['tasks']['parent']['strategy_observation_refs']
        self.assertEqual(len(refs), 1)
        with patch.object(self.plane, '_observe_strategy', side_effect=AssertionError('re-observed')):
            second = self.run_tasks(tasks, resume=True)
        self.assertEqual(second['tasks']['parent']['strategy_observation_refs'], refs)
        self.assertEqual(len(self.calls), 1)
        import json
        record = json.loads((self.plane.state_store.layout.root / refs[0]).read_text())
        self.assertEqual((record['run_id'], record['task_id'], record['attempt']), ('dag-test', 'parent', 0))
        self.assertEqual(record['result_run_id'], 'dag-test-parent')

    def test_attempt_observations_are_distinct(self):
        self.execute_file = lambda *args: {'status':'failed','failure_class':'execution_failed','reason':'same','evidence':[]}
        task = self.task('repair')
        task['repair_candidates'] = [self.task('r1')['entry_request']]
        result = self.run_tasks([task])
        refs = result['tasks']['repair']['strategy_observation_refs']
        self.assertEqual(len(set(refs)), 2)
        import json
        self.assertEqual([json.loads((self.plane.state_store.layout.root / ref).read_text())['attempt'] for ref in refs], [0, 1])

    def test_observation_proposal_is_never_applied(self):
        with patch('unityagent.control_plane.unity_agent_control_plane.observe_execution_strategy', return_value={
                'current_path':'fast', 'recommendation':'promote', 'proposed_path':'orchestrated',
                'reason_codes':['test_proposal'], 'applied':False}):
            result = self.run_tasks([self.task('parent'), self.task('child', ['parent'])])
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(self.calls, ['project.inspect', 'project.inspect'])
        self.assertEqual(result['scheduling'], 'serial')
        self.assertEqual(result['execution_order'], ['parent', 'child'])
        self.assertEqual(result['tasks']['parent']['budget_counts']['global_replans'], 0)
        self.assertEqual(result['tasks']['parent']['result']['handoff']['step_id'], 'inspect_sources')


    def test_saved_dag_baseline_has_attempt_bindings_and_fixed_acceptance(self):
        from tools.adaptive_execution_baseline import build_adaptive_baseline
        result = self.run_tasks([self.task('parent'), self.task('child', ['parent'])])
        baseline = build_adaptive_baseline(self.plane.state_store.layout.root, ['dag-test'], source_revision='fixture')
        self.assertEqual(baseline['observation_completeness'], 'complete')
        samples = [s for group in baseline['groups'] for s in group['samples']]
        self.assertEqual(len(samples), 2)
        self.assertEqual({s['id'] for s in samples}, {'dag-test/parent/0', 'dag-test/child/0'})
        self.assertTrue(all(s['quality'] == 'passed' for s in samples))
        self.assertTrue(all(s['latency_ms'] is not None for s in samples))
        self.assertEqual(len(self.calls), 2)
        # 子Runを明示しなければ、親と子の実行を二重計上しない。
        self.assertEqual(sum(g['completion']['total'] for g in baseline['groups']), len(result['tasks']))
