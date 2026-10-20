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
        from tools.adaptive_baseline import build_adaptive_baseline
        baseline = build_adaptive_baseline(self.plane.state_store.layout.root, ['dag-test'], source_revision='fixture')
        child = next(sample for group in baseline['groups'] for sample in group['samples'] if sample['task_id'] == 'child')
        self.assertEqual(child['execution_status'], 'blocked_dependency')
        self.assertEqual(child['outcome'], 'blocked')

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

    def test_missing_failed_attempt_observation_does_not_inherit_final_success(self):
        from tools.adaptive_baseline import build_adaptive_baseline
        original_execute = self.execute_file
        attempts = []
        def repairable(request, context, arguments):
            attempts.append(request)
            if len(attempts) == 1:
                return {'status': 'failed', 'failure_class': 'execution_failed', 'reason': 'first attempt', 'evidence': []}
            return original_execute(request, context, arguments)
        self.execute_file = repairable
        original_observe = self.plane._observe_strategy
        def observe(result, **kwargs):
            if kwargs.get('attempt') == 0:
                return {**result, 'strategy_observation_refs': []}
            return original_observe(result, **kwargs)
        task = self.task('repair')
        task['repair_candidates'] = [self.task('candidate')['entry_request']]
        with patch.object(self.plane, '_observe_strategy', side_effect=observe):
            result = self.run_tasks([task])
        self.assertEqual(result['status'], 'verified')
        baseline = build_adaptive_baseline(self.plane.state_store.layout.root, ['dag-test'], source_revision='fixture')
        samples = [sample for group in baseline['groups'] for sample in group['samples']]
        self.assertEqual(len(samples), 2)
        self.assertEqual(sum(group['completion']['completed'] for group in baseline['groups']), 1)
        self.assertEqual(samples[0]['execution_status'], 'blocked')
        self.assertEqual(samples[1]['execution_status'], 'completed')


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
        from tools.adaptive_baseline import build_adaptive_baseline
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

    def dag_records(self, result):
        from unityagent.persistence.state.dag_decision import read_dag_decision
        return [read_dag_decision(self.plane.state_store.layout.root, ref, run_id='dag-test')
                for ref in result['dag_decision_refs']]

    def test_parent_boundary_records_remaining_ready_and_immutable_sources(self):
        tasks = [self.task('parent'), self.task('child',['parent'])]
        result = self.run_tasks(tasks)
        records = self.dag_records(result)
        self.assertEqual(len(records),2)
        first, last = records
        self.assertEqual(first['target'], {'kind':'parent_dag','run_id':'dag-test'})
        self.assertEqual(first['boundary']['task_id'],'parent')
        self.assertEqual(first['inputs']['remaining_task_ids'], ['child'])
        self.assertEqual(first['inputs']['ready_task_ids'], ['child'])
        self.assertEqual(first['inputs']['selection_inputs'], {'task_count':1})
        self.assertTrue(all(m['task_id']=='child' for m in first['inputs']['missing_inputs']))
        self.assertIn('parent',first['observed_facts'])
        self.assertEqual(first['observed_facts']['parent']['values']['risk'],'low')
        self.assertNotIn('resource_conflict',first['observed_facts']['parent']['values'])
        self.assertIsNone(first['decision']['current_path'])
        self.assertEqual(last['decision']['reason_codes'], ['no_remaining_tasks'])
        self.assertEqual(self.calls,['project.inspect','project.inspect'])
        # current更新後も最初の根拠は変わらない。
        self.assertEqual(self.plane.state_store.load_task_state('dag-test')['tasks']['child']['status'],'verified')
        self.assertEqual(self.dag_records(result)[0], first)
        self.assertIn('/snapshots/dag-boundary/',first['state_ref'])

    def test_parent_record_does_not_change_execution_or_legacy_baseline(self):
        from tools.adaptive_baseline import build_adaptive_baseline
        tasks = [self.task('parent'), self.task('child',['parent'])]
        result = self.run_tasks(tasks)
        baseline = build_adaptive_baseline(self.plane.state_store.layout.root,['dag-test'],source_revision='fixture')
        self.assertEqual(baseline['observation_completeness'],'complete')
        self.assertEqual(len(baseline['dag_decisions']),2)
        self.assertTrue(all(r['recommendation']=='not_evaluated' for r in baseline['dag_decisions']))
        self.assertEqual(sum(g['quality']['succeeded'] for g in baseline['groups']),2)
        # P0〜P1の子Run観測の意味・Schemaは維持する。
        self.assertEqual(len(result['tasks']['parent']['strategy_observation_refs']),1)
        state = self.plane.state_store.load_task_state('dag-test')
        state.pop('dag_decision_refs')
        self.plane.state_store.save_task_state(state)
        legacy = build_adaptive_baseline(self.plane.state_store.layout.root,['dag-test'],source_revision='fixture')
        self.assertNotIn('dag_decisions',legacy)
        self.assertEqual(sum(g['quality']['succeeded'] for g in legacy['groups']),2)

    def test_parent_boundary_resume_does_not_replay_or_rewrite(self):
        tasks = [self.task('parent')]
        first = self.run_tasks(tasks)
        refs = first['dag_decision_refs']
        with patch('unityagent.control_plane.task_execution.observe_dag_boundary',side_effect=AssertionError('duplicate')):
            second = self.run_tasks(tasks,resume=True)
        self.assertEqual(second['dag_decision_refs'],refs)
        self.assertEqual(len(self.calls),1)

    def test_parent_observation_storage_failure_preserves_results_and_evidence(self):
        from unityagent.persistence.store.atomic_store import write_immutable_json
        def write(path, value):
            if path.parent.name == 'dag-decision':
                raise OSError('observation unavailable')
            return write_immutable_json(path,value)
        with patch('unityagent.control_plane.dag_observation.write_immutable_json',side_effect=write):
            result = self.run_tasks([self.task('parent')])
        self.assertEqual(self.calls,['project.inspect'])
        self.assertEqual(result['status'],'verified')
        self.assertEqual(result['dag_decision_diagnostics'][0]['code'],'dag_decision_persistence_failed')
        self.assertTrue(self.plane.evidence_store.verify_record(result['evidence_refs'][0]))
        from tools.adaptive_baseline import build_adaptive_baseline
        self.assertEqual(build_adaptive_baseline(self.plane.state_store.layout.root,['dag-test'],source_revision='fixture')['observation_completeness'],'failed')

    def test_parent_attempts_and_repair_budget_are_separate(self):
        self.execute_file = lambda *args:{'status':'failed','failure_class':'execution_failed','reason':'same','evidence':[]}
        task=self.task('repair')
        task['repair_candidates']=[self.task('r1')['entry_request']]
        result=self.run_tasks([task,self.task('dependent',['repair'])])
        records=self.dag_records(result)
        self.assertEqual([r['boundary']['attempt'] for r in records],[0,1])
        self.assertEqual(records[0]['inputs']['tasks']['repair']['repair_budget_remaining'],2)
        self.assertEqual(records[1]['inputs']['tasks']['repair']['repair_budget_remaining'],1)
        self.assertEqual(records[0]['inputs']['remaining_task_ids'],['repair','dependent'])
        self.assertEqual(records[1]['inputs']['tasks']['dependent']['dependencies_satisfied'],False)

    def test_parent_record_rejects_tampered_evidence_and_cross_attempt_references(self):
        from unityagent.persistence.state.dag_decision import read_dag_decision
        from unityagent.persistence.store.atomic_store import read_json,write_immutable_json
        result=self.run_tasks([self.task('parent')])
        record=self.dag_records(result)[0]
        layout=self.plane.state_store.layout
        for changes in ({'boundary':record['boundary'] | {'attempt':1}}, {'project_revisions':{'wrong':'sha256:bad'}},
                        {'definition_fingerprint':self.definition | {'graph_revision':'wrong'}}, {'state_ref':'runs/other/snapshots/dag-boundary/absent.json'}):
            changed=record | changes
            path=layout.snapshot('dag-test','dag-decision',sha256_json(changed))
            write_immutable_json(path,changed)
            with self.assertRaises((ValueError,PersistenceError)):
                read_dag_decision(layout.root,str(path.relative_to(layout.root)),run_id='dag-test')
        evidence=layout.evidence(result['evidence_refs'][0])
        value=read_json(evidence)
        value['verification_status']='failed'
        from unityagent.persistence.store.atomic_store import atomic_write_json
        atomic_write_json(evidence,value)
        with self.assertRaises((ValueError,PersistenceError)):
            read_dag_decision(layout.root,result['dag_decision_refs'][0],run_id='dag-test')

    def test_parent_observation_preserves_requests_order_acceptance_and_scope(self):
        tasks=[self.task('a'),self.task('b',['a'])]
        with patch('unityagent.control_plane.task_execution.observe_dag_boundary',return_value=None):
            original=self.run_tasks(tasks)
        original_calls=list(self.calls)
        self.calls.clear()
        self.plane=UnityAgentControlPlane(self.root/'with-observation')
        observed=self.run_tasks(tasks)
        self.assertEqual(self.calls,original_calls)
        self.assertEqual(observed['status'],original['status'])
        self.assertEqual(observed['execution_order'],original['execution_order'])
        for name in ('a','b'):
            self.assertEqual(observed['tasks'][name]['gates'],original['tasks'][name]['gates'])
            self.assertEqual(observed['tasks'][name]['result']['handoff'],original['tasks'][name]['result']['handoff'])
            self.assertEqual(observed['tasks'][name]['budget_counts'],original['tasks'][name]['budget_counts'])

    def test_parent_invalid_reference_is_distinct_from_missing_inputs(self):
        with patch.object(self.plane.evidence_store,'verify_record',side_effect=PersistenceError('evidence_tampered','bad')):
            result=self.run_tasks([self.task('parent')])
        self.assertEqual(result['status'],'verified')
        self.assertEqual(self.calls,['project.inspect'])
        self.assertEqual(result['dag_decision_diagnostics'][0]['code'],'dag_decision_invalid_reference')
        self.assertNotIn('dag_decision_refs',result)

    def test_parent_project_change_does_not_reuse_old_facts(self):
        from unityagent.control_plane.dag_observation import observe_dag_boundary
        from unityagent.persistence.state.dag_decision import read_dag_decision
        tasks=[self.task('parent')]
        self.run_tasks(tasks)
        state=self.plane.state_store.load_task_state('dag-test')
        observe_dag_boundary(self.plane,tasks,state,task_id='parent',attempt=0,
            dispatch_revisions={str(self.project):'sha256:'+'0'*64})
        record=read_dag_decision(self.plane.state_store.layout.root,state['dag_decision_refs'][-1],run_id='dag-test')
        self.assertEqual(record['observed_facts']['parent']['freshness'],'project_revision_changed')
        self.assertEqual(record['observed_facts']['parent']['values'],{})

    def test_parent_raw_payload_and_provider_arguments_are_not_recorded(self):
        original=self.execute_file
        def execute(*args):
            result=original(*args)
            result['sensitive_source']='secret-not-to-persist-in-decision'
            return result
        self.execute_file=execute
        result=self.run_tasks([self.task('parent')])
        import json
        records=self.dag_records(result)
        self.assertNotIn('secret-not-to-persist-in-decision',json.dumps(records))
        root=self.plane.state_store.layout.root
        self.assertNotIn('secret-not-to-persist-in-decision',(root/records[0]['state_ref']).read_text())
