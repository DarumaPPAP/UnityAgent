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
