import copy
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from unityagent.cli import _fingerprint
from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider


class SlowFileProvider(FileProvider):
    def execute(self, request, context, arguments):
        time.sleep(.08)
        return super().execute(request, context, arguments)


class WorkspaceTaskExecutionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plane = UnityAgentControlPlane(self.root / 'state')
        self.definition = _fingerprint()
        self.tasks, self.parameters, projects = [], {}, {}
        for name in ('a', 'b', 'original'):
            project = self.root / name
            for child in ('Assets', 'Packages', 'ProjectSettings', '.git/objects'):
                (project / child).mkdir(parents=True)
            (project / '.git/HEAD').write_text('ref: refs/heads/fixture\n')
            (project / 'Packages/manifest.json').write_text('{"dependencies":{}}')
            (project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.15f1\n')
            snapshot = discover_environment(str(project), editor_processes=[], editor_processes_observed=True).to_dict()
            task = {'id': name, 'workspace': str(project), 'depends_on': ['a', 'b'] if name == 'original' else [],
                'goal': 'Inspect the bound project', 'read_set': ['.'], 'write_set': [], 'resource_claims': [],
                'parallel_safe': name != 'original', 'required_gates': {'project': ['project_fact']},
                'entry_request': {'schema_version': '2.0', 'request_id': name, 'entry_point': 'codex_plugin',
                                  'project_root': str(project), 'intent': {'kind': 'project_inspection'}}}
            self.tasks.append(task)
            self.parameters[name] = {'environment_snapshot': snapshot, 'context': ResolutionContext(policy_allowed=True),
                                     'executors': {'file': SlowFileProvider(project).execute}}
            projects[str(project)] = {'read_set': ['.'], 'write_set': []}
        self.contract = {'goal': 'Inspect isolated projects and verify the original',
            'project_root': str(self.root / 'original'), 'projects': projects,
            'required_gates': {'project': ['project_fact']}, 'approval_conditions': ['existing_policy'],
            'allowed_entry_kinds': ['project_inspection']}

    def run_tasks(self, **kwargs):
        with patch('unityagent.runtime.guardrails.project_lease._default_lock_root', return_value=self.root / 'locks'):
            return self.plane.execute_workspace_tasks(self.tasks, run_id='isolated',
                definition_fingerprint=self.definition, task_parameters=self.parameters,
                root_contract=self.contract, parallel_enabled=kwargs.pop('parallel_enabled', True), **kwargs)

    def test_real_workers_overlap_parent_has_single_writer_and_original_gate_is_serial(self):
        coordinator = threading.get_ident()
        writer = self.plane.state_store.save_task_state
        def save(record):
            self.assertEqual(threading.get_ident(), coordinator)
            return writer(record)
        with patch.object(self.plane.state_store, 'save_task_state', side_effect=save):
            result = self.run_tasks()
        self.assertEqual(result['status'], 'verified', result)
        self.assertEqual(result['execution_order'], ['a', 'b', 'original'])
        self.assertEqual(result['final_gates'], {'project': 'passed'})
        self.assertGreater(result['observed_worker_overlap_ns'], 0)
        self.assertEqual(result['parallel_execution']['max_workers'], 2)
        self.assertEqual(result.get('dag_decision_diagnostics', []), [])
        from tools.adaptive_baseline import build_adaptive_baseline
        baseline = build_adaptive_baseline(self.plane.state_store.layout.root, ['isolated'], source_revision='fixture')
        self.assertEqual(baseline['observation_completeness'], 'complete', baseline)
        self.assertEqual(self.run_tasks(resume=True)['status'], 'verified')

    def test_serial_control_uses_the_same_tasks_without_threads(self):
        with patch('unityagent.runtime.execution_control.isolated_worker_batch.run_isolated_batch') as workers:
            result = self.run_tasks(parallel_enabled=False)
        self.assertEqual(result['status'], 'verified', result)
        self.assertEqual(result['observed_worker_overlap_ns'], 0)
        workers.assert_not_called()

    def test_native_outputs_cannot_target_an_unselected_or_finished_root_project(self):
        from unityagent.runtime.tooling.providers.native_unity_editor.native_unity_editor_provider import NativeUnityEditorProvider
        for name, foreign in (('a', 'b'), ('original', 'a')):
            with self.subTest(task=name):
                self.plane = UnityAgentControlPlane(self.root / ('state-' + name))
                self.parameters['a']['executors'].pop('native_unity_editor', None)
                if name == 'a':
                    self.tasks[1]['depends_on'] = ['a']
                native = NativeUnityEditorProvider(self.root / name,
                    self.parameters[name]['environment_snapshot'], temp_root=self.root / foreign / 'Assets/native-output')
                self.parameters[name]['executors']['native_unity_editor'] = native.execute
                with self.assertRaises(ValueError):
                    self.run_tasks()

    def test_child_failure_blocks_original_without_resending_or_false_gate(self):
        self.parameters['a']['executors']['file'] = lambda *args: {
            'status': 'failed', 'failure_class': 'execution_failed', 'evidence': []}
        result = self.run_tasks()
        self.assertEqual(result['status'], 'blocked')
        self.assertNotIn('original', result['execution_order'])
        self.assertEqual(result['final_gates'], {'project': 'not_observed'})
        self.assertEqual(self.run_tasks(resume=True)['execution_order'], result['execution_order'])

    def test_parallel_mode_cannot_change_on_resume(self):
        self.run_tasks()
        with self.assertRaises(ValueError):
            self.run_tasks(resume=True, parallel_enabled=False)

    def test_identical_replacement_directory_cannot_change_the_physical_root_on_resume(self):
        import shutil
        self.run_tasks()
        original = self.root / 'original'
        backup = self.root / 'old-original'
        original.rename(backup)
        shutil.copytree(backup, original)
        with self.assertRaises(ValueError):
            self.run_tasks(resume=True)

    def test_plan_update_consumes_both_results_only_after_the_worker_barrier(self):
        added = copy.deepcopy(self.tasks[-1])
        added['id'] = 'c'
        added['entry_request']['request_id'] = 'c'
        self.parameters['c'] = self.parameters['original']
        def propose(context):
            if context['plan']['revision']:
                return None
            state = self.plane.state_store.load_task_state('isolated')
            self.assertEqual([state['tasks'][name]['status'] for name in ('a', 'b')], ['verified', 'verified'])
            self.assertEqual(set(state['task_receipt_refs']), {'a', 'b'})
            return {'base_digest': context['plan_digest'], 'tasks': context['plan']['tasks'] + [added],
                    'reason': 'Verify an extra bounded original observation', 'evidence_refs': context['evidence_refs']}
        result = self.run_tasks(plan_proposer=propose)
        self.assertEqual(result['status'], 'verified', result)
        self.assertEqual(result['execution_order'], ['a', 'b', 'c', 'original'])
        self.assertEqual(self.run_tasks(resume=True, plan_proposer=propose)['status'], 'verified')

    def test_single_fast_task_uses_the_existing_inline_dag_without_parallel_records(self):
        self.tasks = [self.tasks[-1]]
        self.tasks[0]['depends_on'] = []
        with patch('unityagent.control_plane.workspace_task_execution._observations') as physical:
            result = self.run_tasks()
        self.assertEqual(result['status'], 'verified', result)
        self.assertNotIn('parallel_execution', result)
        physical.assert_not_called()

    def test_cancelled_fast_task_never_dispatches(self):
        self.tasks = [self.tasks[-1]]
        self.tasks[0]['depends_on'] = []
        cancel = threading.Event()
        cancel.set()
        provider = self.parameters['original']['executors']['file']
        with patch.object(provider.__self__, 'inspect_project', wraps=provider.__self__.inspect_project) as dispatch:
            result = self.run_tasks(cancel_event=cancel)
        self.assertEqual(result['status'], 'blocked')
        dispatch.assert_not_called()

    def test_serial_deadline_never_produces_verified_after_expiry(self):
        result = self.run_tasks(parallel_enabled=False, timeout_seconds=.001)
        self.assertEqual(result['status'], 'blocked')
        self.assertNotEqual(result['final_gates'], {'project': 'passed'})

    def test_unknown_native_output_never_gets_a_fabricated_verified_path(self):
        from unityagent.control_plane.workspace_task_execution import _observations
        for name in ('a', 'b'):
            self.parameters[name]['executors']['native_unity_editor'] = lambda *args: None
        observation = _observations(self.plane, self.tasks[:2], self.parameters,
                                    self.contract['project_root'], 'isolated', self.contract['projects'])
        self.assertEqual(observation['status'], 'blocked')
        with self.assertRaises(ValueError):
            self.run_tasks()

    def test_fast_host_claim_conflict_never_dispatches(self):
        from unityagent.runtime.guardrails.project_lease import acquire_host_claims
        self.tasks = [self.tasks[-1]]
        self.tasks[0]['depends_on'] = []
        self.tasks[0]['resource_claims'] = ['host:shared']
        with patch('unityagent.runtime.guardrails.project_lease._default_lock_root', return_value=self.root / 'locks'):
            with acquire_host_claims(['host:shared'], owner='other'):
                result = self.run_tasks()
        self.assertEqual(result['status'], 'blocked')

    def test_same_workspace_can_be_reused_by_a_later_dependency(self):
        task = copy.deepcopy(self.tasks[0])
        task.update(id='a2', depends_on=['a'])
        task['entry_request']['request_id'] = 'a2'
        self.tasks.append(task)
        self.parameters['a2'] = self.parameters['a']
        result = self.run_tasks()
        self.assertEqual(result['status'], 'verified', result)
        self.assertLess(result['execution_order'].index('a'), result['execution_order'].index('a2'))

    def test_legacy_resume_cannot_consume_parallel_run(self):
        from unityagent.persistence.state.parallel_execution import append_parallel_event
        def interrupt(store, state, phase, **payload):
            ref = append_parallel_event(store, state, phase, **payload)
            if phase == 'accepted':
                raise OSError('interrupted after accepted batch')
            return ref
        with patch('unityagent.control_plane.workspace_task_execution.append_parallel_event', side_effect=interrupt):
            with self.assertRaises(OSError):
                self.run_tasks()
        with self.assertRaises(ValueError):
            self.plane.execute_tasks(self.tasks, run_id='isolated', definition_fingerprint=self.definition,
                task_parameters=self.parameters, root_contract=self.contract, resume=True)

    def test_interrupted_dispatch_is_never_replayed_even_when_state_was_trimmed(self):
        from unityagent.persistence.store.atomic_store import read_json, atomic_write_json
        def interrupted(*args, **kwargs):
            raise OSError('fixture interrupt after dispatching receipt')
        with patch('unityagent.runtime.execution_control.isolated_worker_batch.run_isolated_batch', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.run_tasks()
        path = self.plane.state_store.layout.run_root('isolated') / 'current/task-state.json'
        state = read_json(path)
        state.pop('parallel_execution_refs', None)
        state.pop('parallel_execution', None)
        for record in state['tasks'].values():
            record['status'] = 'pending'
        atomic_write_json(path, state)
        with self.assertRaises(ValueError):
            self.run_tasks(resume=True)
