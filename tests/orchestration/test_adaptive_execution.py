"""Adaptive path and DAG scheduling security/fast path regressions."""
from __future__ import annotations

import unittest
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
