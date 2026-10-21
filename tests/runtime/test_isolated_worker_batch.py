from pathlib import Path
import sys
import tempfile
import threading
import unittest


class IsolatedWorkerBatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.jobs = [{'task_id': name, 'child_run_id': 'parent-' + name, 'attempt': 0,
                      'plan_digest': 'sha256:' + 'a' * 64, 'input_revision': 'sha256:' + 'b' * 64}
                     for name in ('left', 'right')]

    def run_batch(self, execute, prepare=lambda job, value: True, **kwargs):
        from unityagent.runtime.execution_control.isolated_worker_batch import run_isolated_batch
        return run_isolated_batch(self.jobs, execute=execute, prepare=prepare,
                                  timeout_seconds=kwargs.pop('timeout_seconds', 5), **kwargs)

    def execute(self, job, consume, cancel):
        from unityagent.runtime.execution_control.process_runtime import run_streaming_process
        if not consume({'task_id': job['task_id']}):
            return {'run_id': job['child_run_id'], 'status': 'blocked'}
        name = job['task_id']
        process = run_streaming_process([sys.executable, '-c', 'import time; time.sleep(.15)'],
            cwd=self.root, stdout_path=self.root / (name + '.out'), stderr_path=self.root / (name + '.err'),
            timeout_seconds=3, cancel_event=cancel)
        return {'run_id': job['child_run_id'], 'status': 'completed' if process.returncode == 0 else 'blocked',
                'cleanup': process.process_tree_cleanup, 'remaining_processes': process.remaining_processes}

    def test_real_process_workers_overlap_and_preparation_runs_only_on_coordinator(self):
        coordinator = threading.get_ident()
        seen = []
        def prepare(job, value):
            self.assertEqual(threading.get_ident(), coordinator)
            seen.append(job['task_id'])
            return True
        result = self.run_batch(self.execute, prepare)
        self.assertTrue(result['all_workers_stopped'], result)
        self.assertGreater(result['overlap_ns'], 0)
        self.assertEqual(set(seen), {'left', 'right'})
        self.assertTrue(all(item['result']['status'] == 'completed' for item in result['results']))
        self.assertTrue(all(item['result']['remaining_processes'] == 0 for item in result['results']))

    def test_prepare_rejection_prevents_both_dispatches(self):
        launched = []
        def execute(job, consume, cancel):
            if consume({}):
                launched.append(job['task_id'])
            return {'run_id': job['child_run_id'], 'status': 'blocked'}
        result = self.run_batch(execute, lambda job, value: job['task_id'] == 'left')
        self.assertTrue(result['all_workers_stopped'])
        self.assertEqual(launched, [])
        self.assertEqual(result['overlap_ns'], 0)

    def test_failure_before_preparation_releases_other_worker_without_dispatch(self):
        def execute(job, consume, cancel):
            if job['task_id'] == 'left':
                raise RuntimeError('fixture failure')
            return {'run_id': job['child_run_id'], 'status': 'blocked' if not consume({}) else 'bad'}
        result = self.run_batch(execute)
        self.assertTrue(result['all_workers_stopped'])
        self.assertTrue(any(item.get('error_type') == 'RuntimeError' for item in result['results']))

    def test_timeout_uses_existing_process_cancellation_and_cleanup(self):
        def execute(job, consume, cancel):
            from unityagent.runtime.execution_control.process_runtime import run_streaming_process
            if not consume({}):
                return {'run_id': job['child_run_id'], 'status': 'blocked'}
            name = job['task_id']
            process = run_streaming_process([sys.executable, '-c', 'import time; time.sleep(30)'],
                cwd=self.root, stdout_path=self.root / (name + '.out'), stderr_path=self.root / (name + '.err'),
                timeout_seconds=10, cancel_event=cancel)
            return {'run_id': job['child_run_id'], 'status': 'blocked', 'cancelled': process.cancelled,
                    'remaining_processes': process.remaining_processes}
        result = self.run_batch(execute, timeout_seconds=.2)
        self.assertTrue(result['timed_out'])
        self.assertTrue(result['all_workers_stopped'])
        self.assertTrue(all(item['result']['cancelled'] and item['result']['remaining_processes'] == 0
                            for item in result['results']))

    def test_wrong_child_identity_is_never_accepted(self):
        def execute(job, consume, cancel):
            consume({})
            return {'run_id': 'foreign-run', 'status': 'completed'}
        result = self.run_batch(execute)
        self.assertTrue(all(item.get('error_type') == 'WorkerIdentityError' for item in result['results']))

    def test_completed_result_without_the_preparation_barrier_is_rejected(self):
        result = self.run_batch(lambda job, consume, cancel: {'run_id': job['child_run_id'], 'status': 'completed'})
        self.assertTrue(all(item.get('error_type') == 'WorkerIdentityError' for item in result['results']))
