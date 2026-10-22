import copy
import tempfile
import unittest
from pathlib import Path

from unityagent.cli import _fingerprint
from unityagent.orchestration.graph import plan


def task(name, deps=()):
    return {'id': name, 'goal': 'inspect', 'workspace': '/project', 'depends_on': list(deps),
            'read_set': ['.'], 'write_set': [], 'resource_claims': [],
            'required_gates': {'inspection': ['project_fact']},
            'entry_request': {'intent': {'kind': 'project_inspection'}, 'project_root': '/project'}}


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.root = {'goal': 'inspect safely', 'project_root': '/project', 'projects': {'/project': {'read_set': ['.'], 'write_set': []}},
                     'required_gates': {'inspection': ['project_fact']}, 'approval_conditions': ['existing_policy']}
        self.initial = plan.create_plan(run_id='dynamic', root_contract=self.root,
            definition_fingerprint=_fingerprint(), tasks=[task('a'), task('b', ['a'])],
            project_revisions={'/project': 'sha256:' + '1' * 64})
        self.states = {'a': {'status': 'verified'}, 'b': {'status': 'pending'}}

    def proposal(self, tasks=None, **values):
        return {'base_digest': plan.digest(self.initial), 'tasks': tasks or [task('a'), task('extra', ['a']), task('b', ['extra'])],
                'reason': 'additional_inspection', 'evidence_refs': ['evidence-a'], **values}

    def revise(self, proposal=None, **kwargs):
        return plan.revise_plan(self.initial, proposal or self.proposal(), task_states=self.states,
                                evidence_refs=['evidence-a'], proposals_consumed=1, **kwargs)

    def test_observed_addition_and_dependency_update_preserve_root_and_executed_definition(self):
        revised = self.revise()
        self.assertEqual(revised['revision'], 1)
        self.assertEqual(revised['previous_digest'], plan.digest(self.initial))
        self.assertEqual(revised['root_contract'], self.root)
        self.assertEqual([t['id'] for t in revised['tasks']], ['a', 'extra', 'b'])
        self.assertEqual(revised['generated_task_ids'], ['a', 'b', 'extra'])

    def test_cancel_and_split_pending_task_are_explicit_and_cannot_reuse_cancelled_id(self):
        revised = self.revise(self.proposal([task('a'), task('b-one', ['a']), task('b-two', ['b-one'])]))
        self.assertEqual(revised['cancelled_task_ids'], ['b'])
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            plan.revise_plan(revised, {**self.proposal([task('a'), task('b')]), 'base_digest': plan.digest(revised)},
                task_states={'a': {'status': 'verified'}, 'b-one': {'status': 'pending'}, 'b-two': {'status': 'pending'}},
                evidence_refs=['evidence-a'], proposals_consumed=2)

    def test_invalid_updates_are_rejected(self):
        invalid = [self.proposal(base_digest='stale'), self.proposal(evidence_refs=['unknown']),
                   self.proposal([task('a', ['b']), task('b', ['a'])]),
                   self.proposal([task('a'), task('b', ['missing'])]),
                   self.proposal([task('b')])]
        changed = self.proposal()
        changed['tasks'][0]['goal'] = 'rewritten completed task'
        invalid.append(changed)
        changed = self.proposal()
        changed['tasks'][1]['write_set'] = ['Assets/user.cs']
        invalid.append(changed)
        changed = self.proposal()
        changed['tasks'][1]['required_gates'] = {'weak': ['something']}
        invalid.append(changed)
        for proposal in invalid:
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                self.revise(proposal)

    def test_no_update_during_running_attempt_or_after_limits(self):
        with self.assertRaisesRegex(ValueError, 'running'):
            plan.revise_plan(self.initial, self.proposal(), task_states={'a': {'status': 'running'}, 'b': {'status': 'pending'}},
                evidence_refs=['evidence-a'], proposals_consumed=1)
        with self.assertRaisesRegex(ValueError, 'proposal budget'):
            plan.revise_plan(self.initial, self.proposal(), task_states=self.states, evidence_refs=['evidence-a'], proposals_consumed=5)
        too_many = self.proposal([task('a'), *[task('new' + str(i)) for i in range(32)]])
        with self.assertRaisesRegex(ValueError, 'Task budget'):
            self.revise(too_many)


class PlanDurabilityTests(PlanTests):
    def setUp(self):
        super().setUp()
        from unityagent.persistence.state.state_store import StateStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StateStore(self.temp.name)
        self.state = {'schema_version': '2.0', 'run_id': 'dynamic', 'contract_digest': 'initial',
                      'definition_fingerprint': _fingerprint(), 'tasks': self.states,
                      'project_revisions': self.initial['project_revisions'], 'plan_event_refs': []}

    def test_snapshot_alone_is_not_active_and_event_truncation_is_detected(self):
        from unityagent.persistence.state import plan as saved
        ref = saved.stage_plan(self.store.layout, self.initial)
        self.assertNotIn('active_plan_ref', self.state)
        saved.commit_plan(self.store, self.state, ref, expected_ref=None)
        self.assertEqual(saved.read_active_plan(self.store, self.state), self.initial)
        revised = self.revise()
        revised_ref = saved.stage_plan(self.store.layout, revised)
        saved.commit_plan(self.store, self.state, revised_ref, expected_ref=ref)
        current = saved.read_active_plan(self.store, self.state)
        self.assertEqual(current['revision'], 1)
        stale = copy.deepcopy(self.state)
        stale['active_plan_ref'] = ref
        stale['plan_event_refs'].pop()
        self.store.save_task_state(stale)
        (self.store.layout.root / revised_ref).unlink()
        with self.assertRaisesRegex(ValueError, 'journal|history'):
            saved.read_active_plan(self.store, stale)

    def test_stale_activation_is_rejected(self):
        from unityagent.persistence.state import plan as saved
        ref = saved.stage_plan(self.store.layout, self.initial)
        saved.commit_plan(self.store, self.state, ref, expected_ref=None)
        with self.assertRaisesRegex(ValueError, 'base'):
            saved.commit_plan(self.store, self.state, ref, expected_ref=None)


class DynamicExecutionTests(unittest.TestCase):
    from tests.runtime.test_task_dag_execution import TaskDagTests as _fixture
    setUp = _fixture.setUp
    def task(self, name, deps=(), gates=None):
        return {**self._fixture.task(self, name, deps, gates), 'read_set': ['.']}
    execute_file = _fixture.execute_file
    run_tasks = _fixture.run_tasks

    def root_contract(self):
        return {'goal': 'inspect project with additional investigation', 'project_root': str(self.project),
                'projects': {str(self.project): {'read_set': ['.'], 'write_set': []}},
                'required_gates': {'project': ['project_fact']}, 'approval_conditions': ['existing_policy']}

    def test_observed_new_task_is_consumed_and_resume_does_not_redispatch(self):
        tasks = [self.task('a'), self.task('b', ['a'])]
        extra = self.task('extra', ['a'])
        parameters = {name: {'environment_snapshot': self.snapshot,
            'context': __import__('unityagent.runtime.tooling.capability_resolver', fromlist=['ResolutionContext']).ResolutionContext(policy_allowed=True),
            'executors': {'file': self.execute_file}} for name in ('a', 'b', 'extra')}
        proposals = []
        def propose(boundary):
            proposals.append(boundary)
            if boundary['completed_task_id'] != 'a':
                return None
            return {'base_digest': boundary['plan_digest'], 'tasks': [tasks[0], extra, self.task('b', ['extra'])],
                    'reason': 'additional_inspection', 'evidence_refs': boundary['evidence_refs']}
        from unittest.mock import patch
        with patch('unityagent.runtime.guardrails.project_lease._default_lock_root', return_value=self.root / 'locks'):
            result = self.plane.execute_tasks(tasks, run_id='dynamic', definition_fingerprint=self.definition,
                task_parameters=parameters, root_contract=self.root_contract(), plan_proposer=propose, adaptive_strategy_enabled=True)
            self.assertEqual(result['execution_order'], ['a', 'extra', 'b'])
            self.assertEqual(result['status'], 'verified')
            self.assertEqual(len(self.calls), 3)
            resumed = self.plane.execute_tasks(tasks, run_id='dynamic', definition_fingerprint=self.definition,
                task_parameters=parameters, root_contract=self.root_contract(), plan_proposer=propose, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(resumed['execution_order'], ['a', 'extra', 'b'])
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(resumed['plan_proposals_consumed'], 1)
        from tools.adaptive_baseline import build_adaptive_baseline
        baseline = build_adaptive_baseline(self.plane.state_store.layout.root, ['dynamic'], source_revision='fixture')
        self.assertEqual(baseline['observation_completeness'], 'complete', baseline)
        self.assertEqual(sum(g['completion']['completed'] for g in baseline['groups']), 3)

    def test_invalid_proposal_is_durable_and_does_not_block_existing_work(self):
        tasks = [self.task('a'), self.task('b', ['a'])]
        def propose(boundary):
            return {'base_digest': 'stale', 'tasks': tasks, 'reason': 'additional_inspection',
                    'evidence_refs': boundary['evidence_refs']}
        first = self.run_tasks(tasks, root_contract=self.root_contract(), plan_proposer=propose)
        self.assertEqual(first['status'], 'verified')
        self.assertEqual(first['plan_proposals_consumed'], 2)
        second = self.run_tasks(tasks, root_contract=self.root_contract(), plan_proposer=propose, resume=True)
        self.assertEqual(second['plan_proposals_consumed'], 2)
        self.assertEqual(len(self.calls), 2)

    def test_cancelled_pending_task_is_never_prepared_or_dispatched(self):
        tasks = [self.task('a'), self.task('b', ['a'])]
        def propose(boundary):
            return {'base_digest': boundary['plan_digest'], 'tasks': [tasks[0]], 'reason': 'redundant_inspection',
                    'evidence_refs': boundary['evidence_refs']}
        result = self.run_tasks(tasks, root_contract=self.root_contract(), plan_proposer=propose,
                                adaptive_strategy_enabled=True)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['execution_order'], ['a'])
        self.assertEqual(list(result['cancelled_tasks']), ['b'])
        self.run_tasks(tasks, root_contract=self.root_contract(), resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(len(self.calls), 1)

    def test_resume_rejects_plan_snapshot_and_reference_truncation(self):
        from unityagent.persistence.state.plan import read_active_plan
        tasks = [self.task('a'), self.task('b', ['a'])]
        def propose(boundary):
            if boundary['completed_task_id'] == 'a':
                return {'base_digest': boundary['plan_digest'], 'tasks': [tasks[0]], 'reason': 'redundant_inspection',
                        'evidence_refs': boundary['evidence_refs']}
        result = self.run_tasks(tasks, root_contract=self.root_contract(), plan_proposer=propose)
        current = read_active_plan(self.plane.state_store, result)
        path = self.plane.state_store.layout.root / result['active_plan_ref']
        path.unlink()
        result['plan_event_refs'].pop()
        old = self.plane.state_store.layout.snapshot('dag-test', 'plan', current['previous_digest'])
        result['active_plan_ref'] = old.relative_to(self.plane.state_store.layout.root).as_posix()
        self.plane.state_store.save_task_state(result)
        with self.assertRaisesRegex(ValueError, 'history|journal'):
            self.run_tasks(tasks, root_contract=self.root_contract(), resume=True)
        self.assertEqual(len(self.calls), 1)

    def test_project_change_invalidates_prior_gate_without_rewriting_evidence(self):
        from unityagent.control_plane.plan_execution import verify_final_gates
        from unityagent.control_plane.task_execution import project_revision
        tasks = [self.task('a')]
        result = self.run_tasks(tasks, root_contract=self.root_contract())
        evidence = self.plane.evidence_store.get(result['evidence_refs'][0])
        (self.project / 'Assets/changed.cs').write_text('class Changed {}')
        result['project_revisions'] = {str(self.project): project_revision(self.project)}
        verify_final_gates(self.plane, result, tasks)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['final_gates'], {'project': 'not_observed'})
        self.assertEqual(self.plane.evidence_store.get(result['evidence_refs'][0]), evidence)

    def test_runtime_invalid_proposal_rejection_remains_resumable(self):
        tasks = [self.task('a')]
        missing = self.task('missing-runtime-parameters', ['a'])
        def propose(boundary):
            return {'base_digest': boundary['plan_digest'], 'tasks': [tasks[0], missing],
                    'reason': 'additional_inspection', 'evidence_refs': boundary['evidence_refs']}
        result = self.run_tasks(tasks, root_contract=self.root_contract(), plan_proposer=propose)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['plan_proposals_consumed'], 1)
        self.run_tasks(tasks, root_contract=self.root_contract(), resume=True)
        self.assertEqual(len(self.calls), 1)

    def test_rejected_preparation_stops_with_independent_task_pending(self):
        import subprocess
        import sys
        code = '''from tests.runtime.test_dynamic_plan import DynamicExecutionTests
from unittest.mock import patch
case = DynamicExecutionTests()
case.setUp()
try:
    with patch('unityagent.runtime.execution_control.strategy.consume_strategy', side_effect=ValueError('rejected fixture')):
        result = case.run_tasks([case.task('a'), case.task('b')], root_contract=case.root_contract(), adaptive_strategy_enabled=True)
    assert result['status'] == 'blocked'
    assert result['tasks']['b']['status'] == 'pending'
    assert not case.calls
finally:
    case.doCleanups()
'''
        subprocess.run([sys.executable, '-c', code], check=True, timeout=10)

    def test_baseline_rejects_truncated_dynamic_state_and_keeps_all_plan_tasks(self):
        from tools.adaptive_baseline import build_adaptive_baseline
        tasks = [self.task('a'), self.task('b', ['a'])]
        result = self.run_tasks(tasks, root_contract=self.root_contract())
        result['tasks'].pop('b')
        result['execution_order'].remove('b')
        self.plane.state_store.save_task_state(result)
        baseline = build_adaptive_baseline(self.plane.state_store.layout.root, ['dag-test'], source_revision='fixture')
        self.assertEqual(baseline['observation_completeness'], 'failed')
        self.assertEqual(sum(g['completion']['total'] for g in baseline['groups']), 2)
        self.assertEqual(sum(g['quality']['succeeded'] for g in baseline['groups']), 0)

    def test_whole_project_read_is_not_granted_by_an_empty_root_scope(self):
        root = self.root_contract()
        root['projects'][str(self.project)]['read_set'] = []
        with self.assertRaisesRegex(ValueError, 'Scope|read'):
            self.run_tasks([self.task('a')], root_contract=root)
        self.assertEqual(self.calls, [])

    def test_final_gate_rechecks_project_after_planning_callback(self):
        def changed(boundary):
            (self.project / 'Assets/user-change.cs').write_text('class UserChange {}')
        result = self.run_tasks([self.task('a')], root_contract=self.root_contract(), plan_proposer=changed)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['final_gates'], {'project': 'not_observed'})

    def test_completed_task_receipt_and_state_truncation_cannot_replay_provider(self):
        tasks = [self.task('a')]
        result = self.run_tasks(tasks, root_contract=self.root_contract())
        (self.plane.state_store.layout.root / result['task_receipt_refs'].pop('a')).unlink()
        result['tasks']['a'] = {'status': 'pending', 'gates': {'project': 'not_observed'},
                                'handoff_history': [], 'semantic_retries': 0}
        result['execution_order'] = []
        self.plane.state_store.save_task_state(result)
        with self.assertRaisesRegex(ValueError, 'audit|history'):
            self.run_tasks(tasks, root_contract=self.root_contract(), resume=True)
        self.assertEqual(len(self.calls), 1)

    def test_rejected_proposal_receipt_and_state_truncation_cannot_reset_budget(self):
        tasks = [self.task('a')]
        def stale(boundary):
            return {'base_digest': 'stale', 'tasks': tasks, 'reason': 'fixture', 'evidence_refs': boundary['evidence_refs']}
        result = self.run_tasks(tasks, root_contract=self.root_contract(), plan_proposer=stale)
        (self.plane.state_store.layout.root / result['plan_proposal_refs'].pop()).unlink()
        result['plan_proposals_consumed'] = 0
        self.plane.state_store.save_task_state(result)
        with self.assertRaisesRegex(ValueError, 'audit|history'):
            self.run_tasks(tasks, root_contract=self.root_contract(), resume=True)
        self.assertEqual(len(self.calls), 1)

    def test_task_identity_cannot_collide_with_a_reserved_repair_attempt(self):
        tasks = [self.task('a')]
        colliding = self.task('a-repair1', ['a'])
        from unityagent.orchestration.graph.plan import create_plan, revise_plan, digest
        initial = create_plan(run_id='fixture', root_contract=self.root_contract(), definition_fingerprint=self.definition,
                              tasks=tasks, project_revisions={str(self.project): 'sha256:' + '1' * 64})
        with self.assertRaisesRegex(ValueError, 'identity collision'):
            revise_plan(initial, {'base_digest': digest(initial), 'tasks': [*tasks, colliding],
                                  'reason': 'fixture', 'evidence_refs': ['evidence-a']},
                        task_states={'a': {'status': 'verified'}}, evidence_refs=['evidence-a'], proposals_consumed=1)

    def test_cancelled_project_stays_in_root_revision_checks(self):
        other = self.root / 'other-project'
        import shutil
        shutil.copytree(self.project, other)
        a, b, c = self.task('a'), self.task('b', ['a']), self.task('c', ['a'])
        b['workspace'] = b['entry_request']['project_root'] = str(other)
        tasks = [a, b, c]
        root = self.root_contract()
        root['projects'][str(other)] = {'read_set': ['.'], 'write_set': []}
        def propose(boundary):
            if boundary['completed_task_id'] == 'a':
                return {'base_digest': boundary['plan_digest'], 'tasks': [a, c], 'reason': 'redundant_inspection',
                        'evidence_refs': boundary['evidence_refs']}
        result = self.run_tasks(tasks, root_contract=root, plan_proposer=propose, adaptive_strategy_enabled=True)
        self.assertEqual(result['status'], 'verified', result.get('strategy_application_diagnostics'))
        self.assertEqual(result['execution_order'], ['a', 'c'])
        self.assertEqual(set(result['project_revisions']), {str(self.project), str(other)})
        self.run_tasks(tasks, root_contract=root, resume=True, adaptive_strategy_enabled=True)
        self.assertEqual(len(self.calls), 2)

    def test_unknown_entry_proposal_is_recorded_as_rejected_and_can_resume(self):
        tasks = [self.task('a')]
        def propose(boundary):
            unknown = self.task('unknown')
            unknown['entry_request']['intent']['kind'] = 'unknown_intent'
            return {'base_digest': boundary['plan_digest'], 'tasks': [tasks[0], unknown],
                    'reason': 'fixture', 'evidence_refs': boundary['evidence_refs']}
        result = self.run_tasks(tasks, root_contract=self.root_contract(), plan_proposer=propose)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['plan_proposals_consumed'], 1)
        self.run_tasks(tasks, root_contract=self.root_contract(), resume=True)
        self.assertEqual(len(self.calls), 1)

    def test_resume_rejects_foreign_evidence_added_to_parent_history(self):
        tasks = [self.task('a')]
        result = self.run_tasks(tasks, root_contract=self.root_contract())
        result['evidence_refs'].append('foreign-evidence')
        self.plane.state_store.save_task_state(result)
        with self.assertRaisesRegex(ValueError, 'Evidence history'):
            self.run_tasks(tasks, root_contract=self.root_contract(), resume=True)
        self.assertEqual(len(self.calls), 1)
