import unittest


class ReadyTaskBatchTests(unittest.TestCase):
    def task(self, name, *, deps=(), writes=None, claims=(), safe=True):
        return {'id': name, 'workspace': '/projects/' + name, 'depends_on': list(deps),
                'write_set': writes if writes is not None else ['Assets/' + name + '.cs'],
                'resource_claims': list(claims), 'parallel_safe': safe}

    def batch(self, tasks, verified=(), enabled=True, status='verified'):
        from unityagent.orchestration.graph.resource_planning import plan_ready_batch
        return plan_ready_batch(tasks, verified_task_ids=set(verified), parallel_enabled=enabled,
                               workspace_status=status)

    def test_maximum_two_and_serial_control_uses_same_order(self):
        tasks = [self.task(name) for name in ('c', 'b', 'a')]
        self.assertEqual(self.batch(tasks), ['a', 'b'])
        self.assertEqual(self.batch(tasks, enabled=False), ['a'])

    def test_dependencies_open_only_after_verified_acceptance(self):
        tasks = [self.task('a'), self.task('b', deps=['a'])]
        self.assertEqual(self.batch(tasks), ['a'])
        self.assertEqual(self.batch(tasks, verified=['a']), ['b'])

    def test_unknown_workspace_nonparallel_safe_shared_claim_or_overlapping_writes_serialize(self):
        for tasks in ([self.task('a'), self.task('b', safe=False)],
                      [self.task('a', claims=['host:x']), self.task('b', claims=['HOST:X'])],
                      [self.task('a', writes=['Assets/C.cs']), self.task('b', writes=['Assets/C.cs'])]):
            self.assertEqual(self.batch(tasks), ['a'])
        self.assertEqual(self.batch([self.task('a'), self.task('b')], status='serial'), ['a'])

    def test_unknown_dependency_does_not_dispatch(self):
        with self.assertRaises(ValueError):
            self.batch([self.task('a', deps=['unknown'])])
