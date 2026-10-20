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
from tests.runtime.test_control_plane import fingerprint
from tools.adaptive_execution_baseline import build_adaptive_baseline

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
        proof_ref = self.snapshot(run, 'orchestration-decision', {'execution_plan': {'path': 'fast'}})
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
        command = [sys.executable, str(ROOT/'tools/adaptive_execution_baseline.py'), '--persistence-root', str(self.root),
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
