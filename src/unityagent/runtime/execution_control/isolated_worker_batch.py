"""最大2 workerを監視し、親threadだけで準備を受理してからdispatchを開く。"""
from concurrent.futures import ThreadPoolExecutor, wait
from queue import Empty, Queue
import threading
import time


class WorkerIdentityError(ValueError):
    pass


def run_isolated_batch(jobs, *, execute, prepare, timeout_seconds, cancel_event=None,
                       cleanup_grace_seconds=10.0):
    """executeは既存Control Plane入口。任意Shell・Provider選択・永続化を所有しない。"""
    if (not isinstance(jobs, list) or len(jobs) != 2 or timeout_seconds <= 0
            or cleanup_grace_seconds <= 0):
        raise ValueError('A supervised parallel batch requires exactly two bounded workers')
    fields = {'task_id', 'child_run_id', 'attempt', 'plan_digest', 'input_revision'}
    if (any(not fields <= job.keys() for job in jobs)
            or len({job['task_id'] for job in jobs}) != 2
            or len({job['child_run_id'] for job in jobs}) != 2):
        raise ValueError('Parallel worker identities must be complete and distinct')
    messages, closed, cancelled = Queue(), threading.Event(), threading.Event()
    gates = {job['task_id']: {'event': threading.Event(), 'accepted': False, 'dispatch_started_ns': None}
             for job in jobs}
    deadline = time.monotonic() + timeout_seconds
    timed_out = False

    def worker(job):
        name, calls = job['task_id'], 0
        gate = gates[name]
        envelope = {key: job[key] for key in fields}
        envelope['started_ns'] = time.monotonic_ns()
        def consume(preparation):
            nonlocal calls
            calls += 1
            if calls != 1:
                raise WorkerIdentityError('Worker preparation was submitted more than once')
            if closed.is_set() or cancelled.is_set():
                return False
            messages.put((name, preparation))
            while not gate['event'].wait(.02):
                if closed.is_set() or cancelled.is_set():
                    return False
            accepted = gate['accepted'] and not cancelled.is_set() and not closed.is_set()
            if accepted:
                gate['dispatch_started_ns'] = time.monotonic_ns()
            return accepted
        try:
            result = execute(job, consume, cancelled)
            if not isinstance(result, dict) or result.get('run_id') != job['child_run_id']:
                raise WorkerIdentityError('Worker returned another child Run')
            if result.get('status') == 'completed' and (calls != 1 or not gate['accepted']):
                raise WorkerIdentityError('Completed worker skipped the preparation barrier')
            envelope['result'] = result
        except BaseException as exc:
            # SourceやPromptが例外本文へ含まれても親の永続化へコピーしない。
            envelope['error_type'] = type(exc).__name__
        envelope.update(finished_ns=time.monotonic_ns(), dispatch_started_ns=gate['dispatch_started_ns'])
        return envelope

    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='UnityAgentWorkspace')
    futures = {job['task_id']: pool.submit(worker, job) for job in jobs}
    preparations = {}

    def interrupted():
        nonlocal timed_out
        if cancel_event is not None and cancel_event.is_set():
            cancelled.set()
        if time.monotonic() >= deadline:
            timed_out = True
            cancelled.set()
        return cancelled.is_set()

    try:
        while len(preparations) < 2 and not interrupted():
            try:
                name, value = messages.get(timeout=.02)
                if name in preparations:
                    raise WorkerIdentityError('Duplicate prepared worker result')
                preparations[name] = value
            except Empty:
                pass
            if any(future.done() and name not in preparations for name, future in futures.items()):
                break
        accepted = len(preparations) == 2 and not interrupted()
        if accepted:
            # workerは両方とも停止中。この呼出しだけが親stateを書ける。
            decisions = []
            for job in jobs:
                try:
                    decisions.append(prepare(job, preparations[job['task_id']]) is True)
                except (ValueError, OSError, KeyError, TypeError):
                    decisions.append(False)
            accepted = all(decisions) and not interrupted()
        for gate in gates.values():
            gate['accepted'] = accepted
            gate['event'].set()
        while not all(future.done() for future in futures.values()) and not interrupted():
            wait(list(futures.values()), timeout=.02)
        if cancelled.is_set():
            # subprocess停止・process tree cleanupは既存Runnerが行う。
            wait(list(futures.values()), timeout=cleanup_grace_seconds)
        stopped = all(future.done() for future in futures.values())
        results = [futures[job['task_id']].result() for job in jobs if futures[job['task_id']].done()]
        intervals = [(item['dispatch_started_ns'], item['finished_ns']) for item in results
                     if item['dispatch_started_ns'] is not None]
        overlap = max(0, min(end for _, end in intervals) - max(start for start, _ in intervals)) if len(intervals) == 2 else 0
        return {'schema_version': '1.0', 'all_workers_stopped': stopped,
                'timed_out': timed_out, 'cancelled': bool(cancel_event and cancel_event.is_set()),
                'overlap_ns': overlap, 'results': results, 'preparation_accepted': accepted}
    finally:
        closed.set()
        if not all(future.done() for future in futures.values()):
            cancelled.set()
        for gate in gates.values():
            gate['event'].set()
        pool.shutdown(wait=False, cancel_futures=True)
