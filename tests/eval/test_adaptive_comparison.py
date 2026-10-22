import copy
import importlib.util
from pathlib import Path
import unittest


class AdaptiveComparisonTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / 'tools/adaptive_comparison.py'
        spec = importlib.util.spec_from_file_location('comparison', path)
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def samples(self):
        rows = []
        for kind in ('fast', 'dynamic', 'parallel'):
            for round_id in range(33):
                order = self.tool.variant_order(round_id)
                for position, variant in enumerate(order):
                    rows.append({'scenario': kind, 'round': round_id, 'variant': variant, 'position': position,
                        'status': 'failed' if kind == 'dynamic' and variant == 'A' else 'passed',
                        'quality_passed': kind != 'dynamic' or variant != 'A', 'evidence_verified': True,
                        'duration_ns': 80_000_000 if kind == 'parallel' and variant == 'C' else 100_000_000,
                        'coordination_ns': 1000, 'safety_incidents': 0, 'context_preserved': True,
                        'redundant_context_copies': 0, 'workers': 2 if kind == 'parallel' and variant == 'C' else 0,
                        'worktrees': 0, 'preparations': 1, 'project_scans': 1, 'model_calls': 1,
                        'provider_calls': 1, 'unnecessary_calls': 0, 'actual_usage': None})
                    rows[-1]['observed_worker_overlap_ns'] = 10 if kind == 'parallel' and variant == 'C' else 0
        return rows

    def test_fixed_thresholds_and_paired_bootstrap_accept_clear_fixture_improvement(self):
        result = self.tool.evaluate(self.samples(), {'fast': 'fast', 'dynamic': 'dynamic', 'parallel': 'parallel'})
        self.assertEqual(result['status'], 'criteria_met')
        self.assertLess(result['parallel']['parallel']['paired_ratio_ci95'][1], 1)
        self.assertIsNone(result['actual_tokens'])

    def test_missing_failure_or_timeout_cannot_disappear_from_denominator(self):
        for change in ('missing', 'timeout', 'unsafe', 'quality', 'slow', 'context', 'unverified', 'no_workers', 'no_overlap'):
            rows = self.samples()
            row = next(row for row in rows if row['scenario'] == 'parallel' and row['variant'] == 'C' and row['round'] == 10)
            if change == 'missing':
                rows.remove(row)
            elif change == 'timeout':
                row['status'], row['quality_passed'] = 'timeout', False
            elif change == 'unsafe':
                row['safety_incidents'] = 1
            elif change == 'quality':
                row['quality_passed'] = False
            elif change == 'slow':
                for sample in rows:
                    if sample['scenario'] == 'parallel' and sample['variant'] == 'C':
                        sample['duration_ns'] = 99_000_000
            elif change == 'context':
                row['context_preserved'] = False
            elif change == 'no_workers':
                row['workers'] = 0
            elif change == 'no_overlap':
                row['observed_worker_overlap_ns'] = 0
            else:
                row['evidence_verified'] = False
            with self.subTest(change=change):
                self.assertNotEqual(self.tool.evaluate(rows, {'fast': 'fast', 'dynamic': 'dynamic', 'parallel': 'parallel'})['status'], 'criteria_met')

    def test_fast_overhead_and_reordered_or_duplicate_pairs_are_rejected(self):
        for change in ('overhead', 'worker', 'order', 'duplicate'):
            rows = self.samples()
            if change == 'duplicate':
                rows.append(copy.deepcopy(rows[-1]))
            else:
                for row in rows:
                    if row['scenario'] == 'fast' and row['variant'] == 'C':
                        row[{'overhead': 'coordination_ns', 'worker': 'workers', 'order': 'position'}[change]] = {'overhead': 1051, 'worker': 1, 'order': 9}[change]
            with self.subTest(change=change):
                self.assertNotEqual(self.tool.evaluate(rows, {'fast': 'fast', 'dynamic': 'dynamic', 'parallel': 'parallel'})['status'], 'criteria_met')

    def test_collect_stops_and_records_when_source_changes_during_a_command(self):
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        from tests.eval.test_adaptive_scenario import AdaptiveScenarioTests
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            conditions = json.loads(AdaptiveScenarioTests().config(root, 'fast').read_text())['config']
            output = root / 'measurement'
            self.tool.freeze(conditions, output)
            changed = False
            def git(command, **_):
                if 'rev-parse' in command:
                    return SimpleNamespace(stdout=('b' if changed else 'a') * 40)
                return SimpleNamespace(stdout='')
            def execute(*_, **__):
                nonlocal changed
                changed = True
                return SimpleNamespace(timed_out=False, cancelled=False, returncode=0,
                                       remaining_processes=0, process_tree_cleanup='not_required')
            with patch.object(self.tool.subprocess, 'run', side_effect=git), patch.object(self.tool, 'run_streaming_process', side_effect=execute) as launch:
                with self.assertRaises(ValueError):
                    self.tool.collect(output)
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(len(list((output / 'samples').glob('*.json'))), 1)
