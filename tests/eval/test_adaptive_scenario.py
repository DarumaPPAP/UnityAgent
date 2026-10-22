import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from tools import adaptive_scenario as scenario
from unityagent.persistence.store.atomic_store import sha256_json


class AdaptiveScenarioTests(unittest.TestCase):
    def config(self, root, kind):
        config = {'schema_version': '1.0', 'source_sha': 'a' * 40, 'model': 'explicit-model',
            'model_settings': {'reasoning_effort': 'high'}, 'unity_version': '6000.3.15f1',
            'packages': {'com.unity.test-framework': '1.3.9'}, 'os': 'fixture-test', 'hardware': 'fixture-test',
            'warmups': 3, 'pairs': 30, 'primary_metric': 'total_duration_including_preparation_workspaces_integration_final_gates',
            'quality_gates': ['project', 'static', 'compile', 'editmode'], 'timeout_seconds': 120,
            'scenarios': [{'id': item, 'kind': item, 'command': [sys.executable, str(scenario.ROOT / 'tools/adaptive_scenario.py'), '--conditions', '{conditions}', '--scenario', item, '--variant', '{variant}', '--workspace', '{workspace}', '--report', '{report}']} for item in ('fast', 'dynamic', 'parallel')]}
        path = root / 'conditions.json'
        path.write_text(json.dumps({'config': config, 'digest': sha256_json(config)}))
        return path

    def test_fast_c_uses_one_preparation_and_provider_without_workers_or_worktrees(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = scenario.run(conditions_path=self.config(root, 'fast'), scenario_id='fast', variant='C',
                                  workspace=root / 'owned', report_path=root / 'report.json')
            self.assertEqual(report['status'], 'passed', report)
            self.assertEqual((report['workers'], report['worktrees']), (0, 0))
            self.assertEqual((report['preparations'], report['provider_calls'], report['model_calls']), (1, 1, 0))
            self.assertTrue(report['context_preserved'])
            comparison = scenario._tool('adaptive_comparison')
            config = json.loads((root / 'conditions.json').read_text())['config']
            self.assertTrue(comparison._verify_evidence(report, config['source_sha'], root / 'owned', 'fast', config))
            self.assertFalse(comparison._verify_evidence(report, config['source_sha'], root / 'foreign', 'fast', config))
            self.assertFalse(comparison._verify_evidence(report, config['source_sha'], root / 'owned', 'parallel', config))

    def test_dynamic_a_stops_but_b_and_c_execute_the_followup_from_the_current_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            conditions = self.config(root, 'dynamic')
            for variant in 'ABC':
                report = scenario.run(conditions_path=conditions, scenario_id='dynamic', variant=variant,
                    workspace=root / variant, report_path=root / (variant + '.json'))
                self.assertEqual(report['status'], 'blocked' if variant == 'A' else 'passed', report)
                self.assertEqual(report['provider_calls'], 1 if variant == 'A' else 2)
                self.assertEqual(report['workers'], 0)

    def test_parallel_needs_frozen_fixture_authorization_before_any_workspace_or_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                scenario.run(conditions_path=self.config(root, 'parallel'), scenario_id='parallel', variant='C',
                    workspace=root / 'owned', report_path=root / 'report.json')
            self.assertFalse((root / 'owned').exists())

    def test_parallel_cannot_discard_outer_e2e_scope_or_overlap_rejection(self):
        from types import SimpleNamespace
        reports = [
            {'status': 'baseline_failure_observed'},
            {'status': 'approval_required', 'proposals': {'left': {'patch_plan_id': 'a' * 64}, 'right': {'patch_plan_id': 'b' * 64}}},
            {'status': 'integration_approval_required', 'integration': {'integration_plan_id': 'c' * 64}, 'result': {'status': 'blocked'}},
            {'status': 'blocked', 'result': {'status': 'verified', 'observed_worker_overlap_ns': 0}}]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(scenario, '_tool', return_value=SimpleNamespace(run=lambda _: reports.pop(0))):
                _, _, state = scenario._parallel(Path(directory) / 'owned', 'C', {
                    'authorize_owned_fixture_patches': True, 'model_settings': {'reasoning_effort': 'high'},
                    'model': 'explicit', 'timeout_seconds': 120, 'unity_version': '6000.3.15f1',
                    'packages': {'com.unity.test-framework': '1.3.9'}})
            self.assertEqual(state['status'], 'blocked')
