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
                     dict(required_subagents=("graphics_subagent", "performance_subagent"))):
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
