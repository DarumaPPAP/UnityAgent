"""保存済み観測だけを使うBaselineの欠測・改竄・分母を検証する。"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator
from unityagent.persistence.store.atomic_store import sha256_json, write_immutable_json, atomic_write_json, relative_ref
from unityagent.persistence.store.layout import PersistenceLayout
from unityagent.persistence.evidence.evidence_store import EvidenceStore
from tests.runtime.test_control_plane import fingerprint
from tools.adaptive_baseline import build_adaptive_baseline

ROOT = Path(__file__).resolve().parents[2]


class AdaptiveBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'state'
        self.layout = PersistenceLayout(self.root)

    def snapshot(self, run, kind, value):
        path = self.layout.snapshot(run, kind, sha256_json(value))
        write_immutable_json(path, value)
        return relative_ref(self.root, path)

    def make_run(self, run='run-a', *, definition=None, status='completed', gates=None, failure=None, source_revision=None):
        definition = definition or fingerprint()
        manifest = {'run_id': run, 'budget_report': {'estimated_tokens': 123, 'selected_utf8_bytes': 369},
                    'materialized_context': {'definition_fingerprint': definition}}
        manifest_ref = self.snapshot(run, 'context-manifest', manifest)
        proof_ref = self.snapshot(run, 'orchestration-decision', {'execution_plan': {'path': 'fast'}, 'context_manifest_ref': manifest_ref})
        inputs = {'selection_inputs': {}, 'failure_class': failure, 'uncertain_side_effects': False}
        record = {**inputs, 'schema_version':'1.0', 'run_id':run, 'result_run_id':run, 'step_id':'inspect_sources',
            'current_path':'fast', 'proposed_path':None, 'recommendation':'blocked' if failure else 'not_evaluated',
            'reason_codes':[failure or 'missing_or_invalid_selection_inputs'], 'applied':False,
            'definition_fingerprint':definition, 'input_digest':sha256_json({'current_path':'fast', **inputs}),
            'evidence_refs':[], 'result_status':status, 'gates':gates or {},
            'context_manifest_ref':manifest_ref, 'orchestration_decision_ref':proof_ref}
        ref = self.snapshot(run, 'strategy-observation', record)
        state = {'schema_version':'1.0', 'run_id':run, 'status':status, 'definition_fingerprint':definition,
                 'strategy_observation_refs':[ref], 'context_manifest_ref':manifest_ref,
                 'orchestration_decision_ref':proof_ref, 'evidence_refs':[]}
        if source_revision:
            state['source_revision'] = source_revision
        atomic_write_json(self.layout.execution_state(run), state)
        return state, record

    def build(self, *runs):
        return build_adaptive_baseline(self.root, list(runs or ['run-a']), source_revision='revision-a')

    def save_observation(self, state, record):
        state['strategy_observation_refs'] = [self.snapshot(state['run_id'], 'strategy-observation', record)]
        atomic_write_json(self.layout.execution_state(state['run_id']), state)

    def add_evidence(self, record, definition=None):
        evidence_id = record['run_id'] + '-evidence'
        EvidenceStore(self.root).append({'schema_version': '1.1', 'evidence_id': evidence_id,
            'run_id': record['run_id'], 'step_id': record['step_id'], 'source_type': 'fixture',
            'source_ref': None, 'timestamp': None, 'hash': None, 'producer': 'fixture',
            'verification_status': 'passed', 'provenance': ['fixture'],
            'definition_fingerprint': definition or record['definition_fingerprint']})
        record['evidence_refs'] = [evidence_id]
        return evidence_id

    def test_evidence_changes_after_append_cannot_pass_quality(self):
        state, record = self.make_run(gates={'project': 'passed'})
        evidence_id = self.add_evidence(record)
        self.save_observation(state, record)
        self.assertEqual(self.build()['groups'][0]['quality']['succeeded'], 1)
        evidence = json.loads(self.layout.evidence(evidence_id).read_text(encoding='utf-8'))
        evidence['verification_status'] = 'failed'
        atomic_write_json(self.layout.evidence(evidence_id), evidence)
        baseline = self.build()
        self.assertEqual(baseline['observation_completeness'], 'failed')
        self.assertEqual(baseline['groups'][0]['quality']['succeeded'], 0)

    def test_evidence_without_append_event_cannot_pass_quality(self):
        state, record = self.make_run(gates={'project': 'passed'})
        evidence_id = self.add_evidence(record)
        self.save_observation(state, record)
        self.layout.evidence_events('run-a').unlink()
        baseline = self.build()
        self.assertEqual(baseline['observation_completeness'], 'failed')
        self.assertEqual(baseline['groups'][0]['quality']['succeeded'], 0)

    def test_manifest_context_revision_must_match_observation(self):
        state, record = self.make_run(gates={'project': 'passed'})
        manifest = json.loads((self.root / record['context_manifest_ref']).read_text(encoding='utf-8'))
        manifest['materialized_context']['definition_fingerprint']['context_revision'] = 'other-context'
        record['context_manifest_ref'] = self.snapshot('run-a', 'context-manifest', manifest)
        record['orchestration_decision_ref'] = self.snapshot('run-a', 'orchestration-decision', {
            'execution_plan': {'path': 'fast'}, 'context_manifest_ref': record['context_manifest_ref']})
        self.save_observation(state, record)
        self.assertEqual(self.build()['groups'][0]['quality']['succeeded'], 0)

    def test_routing_proof_must_reference_observed_manifest(self):
        state, record = self.make_run(gates={'project': 'passed'})
        record['orchestration_decision_ref'] = self.snapshot('run-a', 'orchestration-decision', {
            'execution_plan': {'path': 'fast'}, 'context_manifest_ref': 'different-manifest'})
        self.save_observation(state, record)
        self.assertEqual(self.build()['groups'][0]['quality']['succeeded'], 0)

    def test_declared_observation_uses_previous_context_definition(self):
        state, record = self.make_run(gates={'project': 'passed'})
        previous_definition = dict(fingerprint(), context_revision='before-observation')
        previous_ref = self.snapshot('run-a', 'context-manifest', {
            'run_id': 'run-a', 'materialized_context': {'definition_fingerprint': previous_definition}})
        evidence_id = self.add_evidence(record, previous_definition)
        proof = {'execution_plan': {'path': 'fast'}, 'context_manifest_ref': record['context_manifest_ref'],
            'previous_context_manifest_ref': previous_ref, 'observation_evidence_refs': [evidence_id]}
        record['orchestration_decision_ref'] = self.snapshot('run-a', 'orchestration-decision', proof)
        self.save_observation(state, record)
        self.assertEqual(self.build()['observation_completeness'], 'complete')
        self.assertEqual(self.build()['groups'][0]['quality']['succeeded'], 1)
        # 前提Observationとして列挙されない旧ContextのEvidenceは再利用できない。
        proof['observation_evidence_refs'] = []
        record['orchestration_decision_ref'] = self.snapshot('run-a', 'orchestration-decision', proof)
        self.save_observation(state, record)
        self.assertEqual(self.build()['groups'][0]['quality']['succeeded'], 0)

    def test_group_by_definition(self):
        self.make_run()
        other = fingerprint() | {'graph_revision':'graph-v2'}
        self.make_run('run-b', definition=other)
        result = self.build('run-a', 'run-b')
        self.assertEqual(len(result['groups']), 2)
        schema = yaml.safe_load((ROOT / 'eval/regression/adaptive-baseline.schema.yaml').read_text())
        Draft202012Validator(schema).validate(result)

    def test_group_by_source_revision(self):
        self.make_run(source_revision='actual-a')
        self.make_run('run-b', source_revision='actual-b')
        self.assertEqual({g['source_revision'] for g in self.build('run-a', 'run-b')['groups']}, {'actual-a','actual-b'})

    def test_missing_usage_is_not_zero(self):
        self.make_run()
        self.assertEqual(self.build()['groups'][0]['model_usage'], {'status':'not_observed','total_tokens':None})
        self.assertIsNone(self.build()['groups'][0]['samples'][0]['latency_ms'])

    def test_context_estimate_is_not_billed_tokens(self):
        self.make_run()
        sample = self.build()['groups'][0]['samples'][0]
        self.assertEqual(sample['context_estimated_tokens'], 123)
        self.assertIsNone(self.build()['groups'][0]['model_usage']['total_tokens'])

    def test_blocked_and_unavailable_are_reported_separately(self):
        self.make_run(status='blocked', failure='approval_denied')
        self.make_run('run-b', status='blocked', failure='environment_unavailable')
        group = self.build('run-a','run-b')['groups'][0]
        self.assertEqual(group['outcomes']['blocked'], 1)
        self.assertEqual(group['outcomes']['unavailable'], 1)
        self.assertEqual(group['quality']['evaluable'], 0)
        self.assertEqual(group['quality']['total'], 2)
        self.assertIsNone(group['quality']['success_rate'])
        self.assertEqual(group['completion']['completed'], 0)

    def test_corrupt_or_cross_run_reference_is_rejected(self):
        state, record = self.make_run(gates={'project':'passed'})
        self.make_run('other')
        original = deepcopy(state)
        other = json.loads(self.layout.execution_state('other').read_text())
        for refs in (['../../escape.json'], other['strategy_observation_refs'], ['runs/run-a/snapshots/strategy-observation/absent.json']):
            with self.subTest(refs=refs):
                state['strategy_observation_refs'] = refs
                atomic_write_json(self.layout.execution_state('run-a'), state)
                result = self.build()
                self.assertEqual(result['observation_completeness'], 'failed')
                self.assertEqual(result['groups'][0]['quality']['succeeded'], 0)
        state = original
        path = self.root / state['strategy_observation_refs'][0]
        record['applied'] = True
        atomic_write_json(path, record)
        atomic_write_json(self.layout.execution_state('run-a'), state)
        self.assertEqual(self.build()['observation_completeness'], 'failed')

    def test_input_digest_and_schema_are_verified_even_with_matching_file_digest(self):
        state, record = self.make_run(gates={'project':'passed'})
        for change in ({'input_digest':'sha256:'+'0'*64}, {'applied': True}, {'extra_secret':'hidden'}):
            with self.subTest(change=change):
                state['strategy_observation_refs'] = [self.snapshot('run-a','strategy-observation',record | change)]
                atomic_write_json(self.layout.execution_state('run-a'), state)
                self.assertEqual(self.build()['observation_completeness'], 'failed')

    def test_duplicate_run_is_not_counted_twice(self):
        self.make_run()
        result = self.build('run-a','run-a')
        self.assertEqual(len(result['groups'][0]['samples']),1)
        self.assertEqual(result['requested_run_ids'], ['run-a'])

    def test_export_does_not_modify_inputs(self):
        self.make_run()
        before = {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.build()
        self.assertEqual(before, {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_no_runtime_or_model_is_launched(self):
        self.make_run()
        with patch('subprocess.run', side_effect=AssertionError('runtime')), patch('subprocess.Popen', side_effect=AssertionError('model')):
            self.assertEqual(self.build()['observation_completeness'], 'complete')

    def test_missing_observation_preserves_completion_denominator(self):
        state, _ = self.make_run()
        state['strategy_observation_refs'] = []
        state['strategy_observation_diagnostics'] = [{'code':'observation_persistence_failed'}]
        atomic_write_json(self.layout.execution_state('run-a'), state)
        result = self.build()
        group = result['groups'][0]
        self.assertEqual(result['observation_completeness'], 'failed')
        self.assertEqual(group['quality']['total'], 1)
        self.assertEqual(group['completion']['completed'], 1)
        self.assertEqual(group['quality']['evaluable'], 0)
        self.assertTrue(group['samples'][0]['missing_observations'])

    def test_cli_does_not_overwrite_existing_output(self):
        self.make_run()
        output = Path(self.temp.name) / 'baseline.json'
        command = [sys.executable, str(ROOT/'tools/adaptive_baseline.py'), '--persistence-root', str(self.root),
                   '--run-id','run-a','--source-revision','revision-a','--output',str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        previous = output.read_bytes()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(previous, output.read_bytes())


    def test_cross_run_evidence_is_not_quality_success(self):
        state, record = self.make_run(gates={'project':'passed'})
        record['evidence_refs'] = ['evidence-other']
        atomic_write_json(self.layout.evidence('evidence-other'), {'evidence_id':'evidence-other','run_id':'other',
            'definition_fingerprint':fingerprint()})
        state['strategy_observation_refs'] = [self.snapshot('run-a', 'strategy-observation', record)]
        atomic_write_json(self.layout.execution_state('run-a'), state)
        baseline = self.build()
        self.assertEqual(baseline['observation_completeness'], 'failed')
        self.assertEqual(baseline['groups'][0]['quality']['succeeded'], 0)

    def test_missing_run_does_not_invent_a_record_digest(self):
        result = self.build('missing-run')
        self.assertEqual(result['observation_completeness'], 'failed')
        sample = result['groups'][0]['samples'][0]
        self.assertIsNone(sample['records'][0]['digest'])
        self.assertEqual(sample['outcome'], 'unavailable')


    def test_blocked_runtime_with_passed_gates_is_not_quality_success(self):
        self.make_run(status='blocked', gates={'project':'passed'})
        group = self.build()['groups'][0]
        self.assertEqual(group['quality']['succeeded'], 0)
        self.assertEqual(group['outcomes']['blocked'], 1)


    def test_runtime_environment_failure_vocabulary_is_unavailable(self):
        for failure in ('unavailable', 'unknown', 'unhealthy', 'ambiguous_binding', 'unsupported', 'backend_not_implemented', 'timeout'):
            with self.subTest(failure=failure):
                self.make_run(failure, status='blocked', failure=failure)
                group = self.build(failure)['groups'][0]
                self.assertEqual(group['outcomes']['unavailable'], 1)
                self.assertEqual(group['quality']['evaluable'], 0)


class StrategyApplicationBaselineTests(unittest.TestCase):
    def setUp(self):
        from tests.runtime.test_task_dag_execution import TaskDagTests
        self.fixture = TaskDagTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.plane.state_store.layout.root

    def build(self):
        return build_adaptive_baseline(self.root, ['dag-test'], source_revision='fixture')

    def save(self, state):
        self.fixture.plane.state_store.save_task_state(state)

    def test_optional_applications_preserve_existing_quality_and_path_metrics(self):
        state = self.fixture.run_tasks([self.fixture.task('a')], adaptive_strategy_enabled=True)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        baseline = self.build()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        applications = baseline['strategy_applications']
        self.assertEqual(applications['phase_counts'], {'prepared': 1, 'accepted': 1, 'dispatching': 1, 'finalized': 1, 'rejected': 0, 'interrupted': 0})
        self.assertEqual(applications['incomplete'], 0)
        self.assertEqual(applications['records'][1]['phase'], 'accepted')
        self.assertTrue(applications['records'][1]['applied'])
        self.assertFalse(applications['records'][1]['completed'])
        self.assertTrue(applications['records'][-1]['completed'])
        from tests.runtime.test_task_dag_execution import TaskDagTests
        disabled = TaskDagTests()
        disabled.setUp()
        self.addCleanup(disabled.doCleanups)
        disabled.run_tasks([disabled.task('a')])
        legacy = build_adaptive_baseline(disabled.plane.state_store.layout.root, ['dag-test'], source_revision='fixture')
        self.assertNotIn('strategy_applications', legacy)
        # 独立した旧形式Runとの比較でも、適用履歴を品質・経路集計へ混ぜない。
        for field in ('quality', 'completion', 'path_distribution', 'recommendation_distribution', 'outcomes', 'model_usage'):
            self.assertEqual(baseline['groups'][0][field], legacy['groups'][0][field])

    def test_deleted_or_truncated_application_refs_cannot_disguise_new_state_as_legacy(self):
        original = self.fixture.run_tasks([self.fixture.task('a'), self.fixture.task('b')], adaptive_strategy_enabled=True)
        for flag, refs in ((True, None), (None, None), (True, original['strategy_application_refs'][:4])):
            with self.subTest(flag=flag, refs=refs):
                state = deepcopy(original)
                if flag is None:
                    state.pop('adaptive_strategy_enabled', None)
                if refs is None:
                    state.pop('strategy_application_refs')
                else:
                    state['strategy_application_refs'] = refs
                self.save(state)
                baseline = self.build()
                self.assertEqual(baseline['observation_completeness'], 'failed')
                self.assertGreater(baseline['strategy_applications']['invalid'], 0)

    def test_accepted_application_is_incomplete_until_finalized(self):
        state = self.fixture.run_tasks([self.fixture.task('a')], adaptive_strategy_enabled=True)
        state['strategy_application_refs'] = state['strategy_application_refs'][:2]
        self.save(state)
        applications = self.build()['strategy_applications']
        self.assertEqual(applications['phase_counts']['accepted'], 1)
        self.assertEqual(applications['phase_counts']['finalized'], 0)
        self.assertEqual(applications['incomplete'], 1)
        self.assertFalse(applications['records'][-1]['completed'])
        self.assertEqual(self.build()['observation_completeness'], 'failed')

    def test_deleted_application_files_and_refs_still_fail_completeness(self):
        state = self.fixture.run_tasks([self.fixture.task('a'), self.fixture.task('b')], adaptive_strategy_enabled=True)
        for ref in state['strategy_application_refs'][4:]:
            (self.root / ref).unlink()
        state['strategy_application_refs'] = state['strategy_application_refs'][:4]
        self.save(state)
        baseline = self.build()
        self.assertEqual(baseline['observation_completeness'], 'failed')
        self.assertGreater(baseline['strategy_applications']['invalid'], 0)

    def test_unreadable_current_state_with_application_snapshots_reports_failure(self):
        self.fixture.run_tasks([self.fixture.task('a')], adaptive_strategy_enabled=True)
        (self.root / 'runs/dag-test/current/task-state.json').write_text('{invalid json')
        baseline = self.build()
        self.assertEqual(baseline['observation_completeness'], 'failed')
        self.assertGreater(baseline['strategy_applications']['invalid'], 0)

    def test_tampered_or_cross_run_application_and_diagnostics_fail_completeness(self):
        state = self.fixture.run_tasks([self.fixture.task('a')], adaptive_strategy_enabled=True)
        original = deepcopy(state)
        event = json.loads((self.root / state['strategy_application_refs'][0]).read_text())
        foreign = self.fixture.plane.state_store.layout.snapshot('other-run', 'strategy-application', sha256_json(event))
        write_immutable_json(foreign, event)
        for refs in (['../../outside.json'], [relative_ref(self.root, foreign)], [state['strategy_application_refs'][-1]] * 2):
            with self.subTest(refs=refs):
                state = deepcopy(original)
                state['strategy_application_refs'] = refs
                self.save(state)
                baseline = self.build()
                self.assertEqual(baseline['observation_completeness'], 'failed')
                self.assertGreater(baseline['strategy_applications']['invalid'], 0)
        state = deepcopy(original)
        state['strategy_application_diagnostics'] = [{'code': 'application_finalization_failed'}]
        self.save(state)
        self.assertEqual(self.build()['observation_completeness'], 'failed')
        state = deepcopy(original)
        self.save(state)
        path = self.root / state['strategy_application_refs'][-1]
        event = json.loads(path.read_text())
        event['applied'] = False
        atomic_write_json(path, event)
        self.assertEqual(self.build()['observation_completeness'], 'failed')

    def test_disabled_mode_has_no_optional_application_aggregate(self):
        self.fixture.run_tasks([self.fixture.task('a')])
        self.assertNotIn('strategy_applications', self.build())

    def test_rejected_application_is_distinct_from_completion(self):
        from unityagent.runtime.execution_control.strategy import consume_strategy
        def reject(*args, **kwargs):
            (self.fixture.project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: changed\n')
            return consume_strategy(*args, **kwargs)
        with patch('unityagent.runtime.execution_control.strategy.consume_strategy', side_effect=reject):
            self.fixture.run_tasks([self.fixture.task('a')], adaptive_strategy_enabled=True)
        applications = self.build()['strategy_applications']
        self.assertEqual(applications['phase_counts']['rejected'], 1)
        self.assertEqual(applications['phase_counts']['interrupted'], 0)
        self.assertFalse(applications['records'][-1]['completed'])

    def test_interrupted_application_is_distinct_from_completion(self):
        def interrupted(*args):
            raise KeyboardInterrupt('fixture interruption')
        self.fixture.execute_file = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.fixture.run_tasks([self.fixture.task('a')], adaptive_strategy_enabled=True)
        baseline = self.build()
        applications = baseline['strategy_applications']
        self.assertEqual(applications['phase_counts']['interrupted'], 1)
        self.assertEqual(applications['phase_counts']['finalized'], 0)
        self.assertEqual(applications['invalid'], 0)
        self.assertFalse(applications['records'][-1]['completed'])
        self.assertEqual(baseline['observation_completeness'], 'failed')
