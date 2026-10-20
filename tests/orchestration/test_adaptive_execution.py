"""Adaptive path and DAG scheduling security/fast path regressions."""
from __future__ import annotations

import unittest
from unittest import mock
from unityagent.orchestration.routing.adaptive_execution import select_execution_path
from unityagent.orchestration.graph.resource_planning import plan_task_batches


def choose(**changes):
    base = dict(task_count=1, simple_task=True, risk="low",
                design_review="not_required", requires_replan=False,
                project_bound=True, scope_known=True, context_profile="tight")
    return select_execution_path(**(base | changes))


def task(identifier, *, workspace="project:main", deps=(), writes=(), claims=(),
         parallel=True):
    return dict(id=identifier, workspace=workspace, depends_on=list(deps),
                write_set=list(writes), resource_claims=list(claims),
                parallel_safe=parallel)


class AdaptiveExecutionTests(unittest.TestCase):
    def test_fast_has_no_extra_subagent_graph_or_worktree(self):
        plan = choose()
        self.assertEqual(plan["path"], "fast")
        self.assertEqual(plan["subagent_ids"], [])
        self.assertFalse(plan["parent_graph_required"])
        self.assertFalse(plan["worktree_required"])
        self.assertTrue(plan["evidence_required"])
        self.assertEqual(plan["approval_required"], "consult_policy")

    def test_explicit_subagent_routes_to_one_standard_worker(self):
        plan = choose(requested_subagent="graphics_subagent")
        self.assertEqual(plan["path"], "standard")
        self.assertEqual(plan["subagent_ids"], ["graphics_subagent"])

    def test_risk_review_and_context_require_standard(self):
        for args in (dict(risk="medium"), dict(design_review="required"),
                     dict(requires_replan=True), dict(context_profile="wide"),
                     dict(simple_task=False)):
            with self.subTest(args=args):
                self.assertEqual(choose(**args)["path"], "standard")

    def test_conflict_multi_task_or_multi_subagent_requires_graph(self):
        for args in (dict(task_count=2), dict(resource_conflict=True),
                     dict(required_subagents=("graphics_subagent", "qa_subagent"))):
            with self.subTest(args=args):
                self.assertEqual(choose(**args)["path"], "orchestrated")
                self.assertTrue(choose(**args)["parent_graph_required"])

    def test_incompatible_manual_agent_fails_closed(self):
        plan = choose(requested_subagent="artist_subagent",
                      required_subagents=("graphics_subagent",))
        self.assertEqual(plan["status"], "blocked")
        self.assertIsNone(plan["path"])

    def test_unknown_inputs_do_not_grant_fast_path(self):
        self.assertEqual(choose(scope_known=False)["status"], "blocked")
        self.assertEqual(choose(project_bound=False)["status"], "blocked")
        for args in (dict(risk="unknown"), dict(task_count=0), dict(project_bound=None),
                     dict(requested_subagent="anything")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                choose(**args)

    def test_read_only_independent_tasks_can_share_wave(self):
        value = plan_task_batches([task("a"), task("b")])
        self.assertEqual(value["batches"][0]["task_ids"], ["a", "b"])
        self.assertEqual(value["batches"][0]["execution"], "parallel")

    def test_same_main_project_serializes_reads_during_writes(self):
        value = plan_task_batches([task("a", writes=["Assets/Scene.unity"]),
                                   task("b"), task("c", writes=["Assets/Shader.shader"])])
        self.assertEqual([b["task_ids"] for b in value["batches"]], [["a"], ["b"], ["c"]])

    def test_independent_worktrees_can_run_in_parallel(self):
        value = plan_task_batches([task("a", workspace="worktree:A", writes=["Assets/A.cs"]),
                                   task("b", workspace="worktree:B", writes=["Assets/B.cs"])])
        self.assertEqual(value["batches"][0]["task_ids"], ["a", "b"])

    def test_global_gpu_or_device_claim_is_exclusive_across_worktrees(self):
        value = plan_task_batches([task("a", workspace="worktree:A", claims=["gpu:0"]),
                                   task("b", workspace="worktree:B", claims=["gpu:0"])])
        self.assertEqual([b["task_ids"] for b in value["batches"]], [["a"], ["b"]])

    def test_dependencies_override_parallelism(self):
        value = plan_task_batches([task("c", deps=["a", "b"]), task("a"), task("b")])
        self.assertEqual([b["task_ids"] for b in value["batches"]], [["a", "b"], ["c"]])

    def test_fail_closed_on_cycle_missing_dep_unbound_workspace(self):
        for tasks in (
            [task("a", deps=["b"]), task("b", deps=["a"])],
            [task("a", deps=["missing"])],
            [task("a", workspace="")],
            [task("a"), task("a")],
            [task("a", claims=["../escape"])],
        ):
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                plan_task_batches(tasks)


if __name__ == "__main__":
    unittest.main()


class StrategyObservationTests(unittest.TestCase):
    def observe(self, current_path='fast', **changes):
        from unityagent.orchestration.routing.adaptive_execution import observe_execution_strategy
        inputs = dict(task_count=1, simple_task=True, risk='low', design_review='not_required',
                      requires_replan=False, project_bound=True, scope_known=True)
        inputs.update(changes)
        return observe_execution_strategy(current_path=current_path, selection_inputs=inputs)

    def test_observe_keep_fast(self):
        value = self.observe()
        self.assertEqual((value['recommendation'], value['proposed_path'], value['applied']), ('keep', 'fast', False))

    def test_observe_promote_specialist(self):
        self.assertEqual(self.observe(required_subagents=('qa_subagent',))['proposed_path'], 'standard')
        self.assertEqual(self.observe(required_subagents=('qa_subagent',))['recommendation'], 'promote')

    def test_observe_promote_multiple_tasks(self):
        self.assertEqual(self.observe(task_count=2)['proposed_path'], 'orchestrated')

    def test_observe_demote_single_remaining_task(self):
        self.assertEqual(self.observe('orchestrated')['recommendation'], 'demote')

    def test_observe_blocked_failure_never_promotes(self):
        from unityagent.orchestration.routing.adaptive_execution import observe_execution_strategy
        for failure in ('approval_required', 'approval_denied', 'scope_denied', 'environment_unavailable',
                        'resource_conflict', 'resource_busy', 'context_insufficient', 'unknown_failure'):
            with self.subTest(failure=failure):
                value = observe_execution_strategy(current_path='fast', selection_inputs={}, failure_class=failure)
                self.assertEqual(value['recommendation'], 'blocked')
                self.assertIsNone(value['proposed_path'])
                self.assertIn(failure, value['reason_codes'])
        value = observe_execution_strategy(current_path='fast', selection_inputs={}, uncertain_side_effects=True)
        self.assertIn('uncertain_side_effects', value['reason_codes'])
        for inputs in ({'resource_conflict': True}, {'scope_known': False}, {'project_bound': False}):
            self.assertEqual(self.observe(**inputs)['recommendation'], 'blocked')

    def test_observe_missing_and_invalid_facts(self):
        from unityagent.orchestration.routing.adaptive_execution import observe_execution_strategy
        self.assertEqual(observe_execution_strategy(current_path='fast', selection_inputs={})['recommendation'], 'not_evaluated')
        for inputs in ({'task_count': True}, {'risk': 'unknown'}, {'risk': []}, {'current_path': 'unknown'}):
            self.assertEqual(self.observe(**inputs)['recommendation'], 'not_evaluated')

    def test_observe_does_not_mutate_inputs(self):
        from copy import deepcopy
        from unityagent.orchestration.routing.adaptive_execution import observe_execution_strategy
        inputs = {'task_count': 1, 'secret': {'token': 'not-for-record'}}
        original = deepcopy(inputs)
        value = observe_execution_strategy(current_path='fast', selection_inputs=inputs)
        self.assertEqual(inputs, original)
        self.assertNotIn('secret', str(value))


    def test_invalid_failure_inputs_are_not_evaluated(self):
        from unityagent.orchestration.routing.adaptive_execution import observe_execution_strategy
        for changes in ({'failure_class':True}, {'uncertain_side_effects':'unknown'}):
            result = observe_execution_strategy(current_path='fast', selection_inputs={}, **changes)
            self.assertEqual(result['recommendation'], 'not_evaluated')
            self.assertIsNone(result['proposed_path'])


class DagInputTests(unittest.TestCase):
    def build(self, statuses, facts=None, **kwargs):
        from unityagent.orchestration.routing.adaptive_execution import build_dag_inputs
        tasks = [{'id':name, 'depends_on':deps, 'semantic_repair_limit':2, 'repair_candidates':[]} for name,deps in [('a',[]),('b',['a']),('c',[])]]
        state = {'tasks':{name:{'status':status,'gates':{'project':'passed' if status == 'verified' else 'not_observed'}, 'semantic_retries':0} for name,status in zip(('a','b','c'), statuses)}}
        return build_dag_inputs(tasks, state, task_facts=facts or {}, **kwargs)

    def facts(self):
        return dict(simple_task=True, risk='low', design_review='not_required', requires_replan=False,
                    project_bound=True, scope_known=True, resource_conflict=False, context_profile='tight',
                    required_subagents=(), requested_subagent=None)

    def test_remaining_and_ready_are_different(self):
        before = self.build(['pending','pending','pending'])
        after = self.build(['verified','pending','pending'])
        self.assertEqual(before['remaining_task_ids'], ['a','b','c'])
        self.assertEqual(before['ready_task_ids'], ['a','c'])
        self.assertEqual(after['remaining_task_ids'], ['b','c'])
        self.assertEqual(after['ready_task_ids'], ['b','c'])
        self.assertEqual(after['selection_inputs'], {'task_count':2})

    def test_failed_and_dependency_blocked_are_not_removed(self):
        value = self.build(['blocked','blocked_dependency','pending'])
        self.assertEqual(value['remaining_task_ids'], ['a','b','c'])
        self.assertEqual(value['tasks']['a']['category'], 'failed')
        self.assertEqual(value['tasks']['b']['category'], 'blocked_dependency')
        self.assertEqual(value['ready_task_ids'], ['c'])

    def test_complete_boundary_does_not_select_zero_tasks(self):
        with unittest.mock.patch('unityagent.orchestration.routing.adaptive_execution.select_execution_path', side_effect=AssertionError('zero')):
            value = self.build(['verified']*3)
        self.assertEqual(value['decision']['reason_codes'], ['no_remaining_tasks'])
        self.assertIsNone(value['decision']['candidate_path'])

    def test_complete_facts_reuse_selector_without_comparing_child_path(self):
        facts = {'b':self.facts(), 'c':self.facts()}
        value = self.build(['verified','pending','pending'], facts)
        self.assertEqual(value['decision']['candidate_path'], 'orchestrated')
        self.assertIsNone(value['decision']['current_path'])
        self.assertEqual(value['decision']['recommendation'], 'not_evaluated')
        self.assertIn('parent_strategy_not_observed', value['decision']['reason_codes'])
        self.assertFalse(value['decision']['applied'])
        with_parent = self.build(['verified','pending','pending'], facts, current_path='orchestrated')
        self.assertEqual(with_parent['decision']['recommendation'], 'keep')

    def test_missing_future_facts_are_not_copied_from_completed_task(self):
        value = self.build(['verified','pending','pending'], {'a':self.facts()})
        self.assertEqual(value['selection_inputs'], {'task_count':2})
        self.assertTrue(any(m['task_id']=='b' and m['field']=='risk' for m in value['missing_inputs']))
        self.assertIsNone(value['decision']['candidate_path'])

    def test_stop_reasons_and_running_are_not_resolved_by_coordination(self):
        for failure in ('blocked_by_approval','scope_violation','unavailable','resource_conflict'):
            value = self.build(['blocked','pending','pending'], failure_classes=[failure])
            self.assertEqual(value['decision']['recommendation'], 'blocked')
            self.assertIn(failure,value['decision']['reason_codes'])
            self.assertIsNone(value['decision']['candidate_path'])
        value = self.build(['running','pending','pending'])
        self.assertEqual(value['decision']['recommendation'], 'blocked')
        self.assertIn('uncertain_side_effects',value['decision']['reason_codes'])

    def test_invalid_facts_do_not_become_boolean_defaults(self):
        invalid = self.facts() | {'project_bound':'unknown','simple_task':None,'risk':'unknown'}
        value = self.build(['verified','pending','pending'],{'b':invalid,'c':self.facts()})
        self.assertNotIn('project_bound',value['selection_inputs'])
        self.assertNotIn('simple_task',value['selection_inputs'])
        self.assertTrue(any(m['reason']=='invalid_boundary_fact' for m in value['missing_inputs']))

    def test_acceptance_failure_is_a_blocker_without_failure_class(self):
        value=self.build(['blocked','pending','pending'])
        self.assertEqual(value['decision']['recommendation'],'blocked')
        self.assertIn('task_acceptance_blocked',value['decision']['reason_codes'])

    def test_terminal_boundary_with_known_parent_never_calls_selector(self):
        with mock.patch('unityagent.orchestration.routing.adaptive_execution.select_execution_path',side_effect=AssertionError('terminal')):
            result=self.build(['verified']*3,current_path='fast')
        self.assertEqual(result['decision']['reason_codes'],['no_remaining_tasks'])

    def test_unavailable_status_is_not_unexecuted(self):
        value=self.build(['unavailable','pending','pending'])
        self.assertEqual(value['tasks']['a']['category'],'unavailable')
        self.assertNotIn('a',value['ready_task_ids'])

    def test_verified_status_with_failed_acceptance_is_invalid(self):
        from unityagent.orchestration.routing.adaptive_execution import build_dag_inputs
        with self.assertRaises(ValueError):
            build_dag_inputs([{'id':'a'}],{'tasks':{'a':{'status':'verified','gates':{'gate':'failed'}}}})

    def test_pending_dependents_distinguish_waiting_from_blocked(self):
        waiting=self.build(['pending','pending','pending'])
        blocked=self.build(['blocked','pending','pending'])
        self.assertEqual(waiting['tasks']['b']['category'],'waiting_dependency')
        self.assertEqual(blocked['tasks']['b']['category'],'blocked_dependency')
        self.assertEqual(blocked['tasks']['b']['status'],'pending')

    def test_context_binding_does_not_fill_unknown_scope(self):
        from unityagent.orchestration.routing.adaptive_execution import facts_from_boundary
        proof={'task_contract_projection':{'risk_level':'R0'},'task_fingerprint':{'project_access':'authorized'},
               'execution_plan':{'subagent_ids':[]},'mutation_scope':None}
        manifest={'unresolved_bindings':[],'budget_report':{'profile':'tight'}}
        facts=facts_from_boundary({'entry_request':{'intent':{'kind':'project_inspection'}}},proof,manifest,
            {'decision':'exit'},attempt=0,same_revision=True,proof_ref='proof',manifest_ref='manifest')
        self.assertNotIn('scope_known',facts['values'])
        self.assertIn('scope_known',facts['requires_revalidation'])
