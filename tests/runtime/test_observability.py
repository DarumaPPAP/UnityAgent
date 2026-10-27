"""観測の正確さ・秘密情報の隔離・観測失敗による再実行の防止を確認する。"""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class ExecutionMeasurementTests(unittest.TestCase):
    def plane(self, root):
        return SimpleNamespace(state_store=SimpleNamespace(layout=SimpleNamespace(root=Path(root))))

    def test_projection_failure_never_retries_or_changes_an_execution(self):
        from unityagent.control_plane.measurement import measured
        with tempfile.TemporaryDirectory() as root:
            calls = []
            with patch('unityagent.control_plane.measurement.OperationalEventStore', side_effect=OSError('disk full')):
                with measured(self.plane(root), 'run', 'provider'):
                    calls.append('mutated once')
            self.assertEqual(calls, ['mutated once'])

    def test_source_exception_is_preserved_without_logging_its_message(self):
        from unityagent.control_plane.measurement import measured
        with tempfile.TemporaryDirectory() as root:
            failure = ValueError('private source prompt')
            with self.assertRaises(ValueError) as raised:
                with measured(self.plane(root), 'run', 'provider'):
                    raise failure
            self.assertIs(raised.exception, failure)
            log = (Path(root) / 'operations/metric.jsonl').read_text()
            self.assertNotIn('private', log)
            self.assertIn('duration', log)

    def test_unmeasured_usage_is_omitted_and_fixed_counters_are_numeric(self):
        from unityagent.control_plane.measurement import measured
        with tempfile.TemporaryDirectory() as root:
            with measured(self.plane(root), 'run', 'context') as metrics:
                metrics['selected_utf8_bytes'] = 123
                metrics['estimated_tokens'] = 31
                metrics['input_tokens'] = None
                metrics['prompt'] = 'private'
            log = (Path(root) / 'operations/metric.jsonl').read_text()
            self.assertNotIn('private', log)
            self.assertNotIn('input_tokens', log)
            self.assertIn('selected_utf8_bytes', log)

    def test_usage_projection_keeps_nulls_and_rejects_free_text_keys(self):
        from unityagent.control_plane.measurement import record_model_usage
        with tempfile.TemporaryDirectory() as root:
            record_model_usage(self.plane(root), 'run', {'input_tokens': None, 'output_tokens': None,
                'configured_model': 'explicit-model', 'model_revision': None, 'scope': 'all_observed_completed_turns',
                'unit': 'tokens', 'prompt': 'private source'})
            log = (Path(root) / 'operations/trace.jsonl').read_text()
            self.assertIn('"input_tokens":null', log)
            self.assertNotIn('private', log)


class ModelUsageTests(unittest.TestCase):
    def observe(self, events):
        from unityagent.runtime.telemetry.model_usage import observe_codex_usage
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            path.write_text('\n'.join(json.dumps(event) for event in events), encoding='utf-8')
            return observe_codex_usage(path, model='configured-model', reasoning_effort='high')

    def test_missing_usage_is_null_and_does_not_copy_free_text(self):
        result = self.observe([{'type': 'item.completed', 'text': 'private source prompt'}])
        self.assertIsNone(result['input_tokens'])
        self.assertIsNone(result['output_tokens'])
        self.assertIsNone(result['model_revision'])
        self.assertNotIn('private', json.dumps(result))

    def test_completed_turn_usage_sums_cache_as_subset_of_input(self):
        result = self.observe([{'type': 'turn.completed', 'usage': {
            'input_tokens': 20, 'cached_input_tokens': 10, 'output_tokens': 3}},
            {'type': 'turn.completed', 'usage': {
                'input_tokens': 5, 'cached_input_tokens': 2, 'output_tokens': 4}}])
        self.assertEqual(result['input_tokens'], 25)
        self.assertEqual(result['cached_input_tokens'], 12)
        self.assertEqual(result['output_tokens'], 7)
        self.assertEqual(result['completed_turns'], 2)
        self.assertEqual(result['usage_source'], 'codex.turn.completed.usage')

    def test_partial_malformed_or_boolean_usage_is_not_reported_as_complete(self):
        for usage in ({'input_tokens': True, 'output_tokens': 2},
                      {'input_tokens': -1, 'output_tokens': 2},
                      {'input_tokens': 2, 'cached_input_tokens': 3, 'output_tokens': 2},
                      {'input_tokens': 2}):
            with self.subTest(usage=usage):
                result = self.observe([{'type': 'turn.completed', 'usage': usage}])
                self.assertIsNone(result['input_tokens'])
                self.assertIsNone(result['output_tokens'])

    def test_missing_cache_does_not_invent_zero_or_discard_other_usage(self):
        result = self.observe([{'type': 'turn.completed', 'usage': {
            'input_tokens': 20, 'output_tokens': 3}}])
        self.assertEqual(result['input_tokens'], 20)
        self.assertIsNone(result['cached_input_tokens'])


class PersistenceMeasurementTests(unittest.TestCase):
    def test_only_new_snapshots_count_bytes_and_failed_telemetry_does_not_undo_writes(self):
        from unityagent.persistence.store.measurement import capture
        from unityagent.persistence.store.atomic_store import write_immutable_json, read_json
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'snapshots/context/one.json'
            events = []
            with capture(lambda *event: events.append(event)):
                write_immutable_json(path, {'text': '日本語'})
                write_immutable_json(path, {'text': '日本語'})
            self.assertEqual([event[1] for event in events if event[0] == 'snapshot.bytes'], [path.stat().st_size])
            def unavailable(*_):
                raise OSError('telemetry unavailable')
            with capture(unavailable):
                write_immutable_json(path.parent / 'two.json', {'text': 'retained'})
            self.assertEqual(read_json(path.parent / 'two.json')['text'], 'retained')

    def test_capture_is_local_and_reports_real_repeated_reads(self):
        from unityagent.persistence.store.measurement import capture, observed
        calls, events = [], []
        @observed('evidence.verify')
        def verify():
            calls.append(1)
            return 'verified'
        with capture(lambda *event: events.append(event)):
            verify()
            verify()
        verify()
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event[1] >= 0 for event in events))
