import sys
import tempfile
import unittest
from pathlib import Path
from Runtime.Harnesses.validation_session import ValidationSession


class ValidationSessionTests(unittest.TestCase):
    def test_reuse_and_changed_inputs_execute_real_command(self):
        with tempfile.TemporaryDirectory() as directory:
            counter = Path(directory) / 'count'
            command = [sys.executable, '-c', "from pathlib import Path; p=Path('count'); p.write_text(p.read_text()+'x' if p.exists() else 'x')"]
            session = ValidationSession('R1')
            args = dict(command=command, cwd=directory, timeout_seconds=5, input_fingerprint='source-and-environment-v1')
            self.assertFalse(session.run(**args)['reused'])
            self.assertTrue(session.run(**args)['reused'])
            self.assertEqual(counter.read_text(), 'x')
            session.run(**{**args, 'input_fingerprint': 'source-and-environment-v2'})
            self.assertEqual(counter.read_text(), 'xx')
            session.run(**args, reason='new unresolved risk')
            self.assertEqual(counter.read_text(), 'xxx')

    def test_failed_revalidation_evicts_pass(self):
        from unittest.mock import patch
        session = ValidationSession('R1')
        args = dict(command=['test'], cwd='.', timeout_seconds=5, input_fingerprint='v1')
        with patch('Runtime.Harnesses.command_harness.run_command_harness', side_effect=[{'status':'passed'}, {'status':'failed'}, {'status':'passed'}]) as run:
            session.run(**args)
            session.run(**args, reason='new risk')
            self.assertFalse(session.run(**args)['reused'])
            self.assertEqual(run.call_count, 3)

    def test_small_change_full_suite_needs_reason(self):
        session = ValidationSession('R1')
        with self.assertRaises(ValueError):
            session.run(command=['not-launched'], cwd='.', timeout_seconds=1, input_fingerprint='v1', scope='full')
        with self.assertRaises(ValueError):
            ValidationSession('unknown')

    def test_required_full_gate_is_allowed_and_failures_not_cached(self):
        session = ValidationSession('R1')
        args = dict(command=[sys.executable, '-c', 'raise SystemExit(1)'], cwd='.', timeout_seconds=5, input_fingerprint='v1', scope='full', reason='mandatory repository gate')
        self.assertEqual(session.run(**args)['status'], 'failed')
        self.assertFalse(session.run(**args)['reused'])


if __name__ == '__main__':
    unittest.main()
