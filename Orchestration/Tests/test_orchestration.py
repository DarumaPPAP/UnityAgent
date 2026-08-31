from __future__ import annotations
import sys
import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Orchestration.Graph.health_checks import execute_health_check
from Orchestration.Graph.local_loop import decide_local_loop
from Orchestration.Graph.parallel import plan_parallel
from Orchestration.Graph.state_mapping import loop_control_state_patch, workflow_state_patch
from Orchestration.Graph.todo_selector import select_todo
from Orchestration.Orchestrator.orchestrator import fast_path, load_graph, transition
from Orchestration.Routing.route_selector import load_routes, select_route

GRAPH_PATH = ROOT / "Orchestration/Definitions/development-parent-graph.yaml"
ROUTE_PATH = ROOT / "Orchestration/Routing/task-routes.yaml"


def fingerprint(**overrides):
    base = {"intent": "fix", "artifact": "csharp", "scope": "local", "failure_mode": "runtime", "architecture_state": "decided", "mutation_target": "source", "evidence_state": "known", "project_access": "authorized"}
    base.update(overrides)
    return base


class FakeHealthPort:
    def __init__(self, status): self.status = status
    def probe(self, request):
        return {"schema_version": "1.0", "status": self.status, "check_id": "x", "run_id": "r", "step_id": "s", "kind": "environment", "target": "fixture", "observed_at": "2026-08-29T00:00:00+00:00", "evidence_refs": [], "details": {}, "runtime_profile_revision": "r", "tool_schema_revision": "t"}


class Phase4OrchestrationTests(unittest.TestCase):
    def test_graph_contract_and_topology(self):
        graph = load_graph(GRAPH_PATH)
        schema = yaml.safe_load((ROOT / "Orchestration/Contracts/graph-definition.schema.yaml").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(graph)
        self.assertEqual([item["id"] for item in graph["subgraphs"]], ["planning", "design_review", "investigation", "implementation", "validation", "delivery"])
        nodes = {node["id"] for sg in graph["subgraphs"] for node in sg["nodes"]}
        for loop in graph["local_loops"]:
            sg = next(item for item in graph["subgraphs"] if item["id"] == loop["subgraph_id"])
            local_nodes = {node["id"] for node in sg["nodes"]}
            self.assertIn(loop["from_node_id"], local_nodes)
            self.assertIn(loop["to_node_id"], local_nodes)
            self.assertIn(loop["from_node_id"], nodes)

    def test_semantic_loop_has_no_runtime_limits(self):
        loop = {"continue_on": ["more"], "replan_on": ["invalid"], "exit_on": ["done"]}
        value = decide_local_loop(loop, outcome="more", semantic_attempt=0, progress_marker="p", progress_made=True)
        self.assertEqual(value["decision"], "continue")
        value = decide_local_loop(loop, outcome="more", semantic_attempt=1, progress_marker="p", progress_made=False)
        self.assertEqual(value["decision"], "replan")
        with self.assertRaises(ValueError):
            decide_local_loop({**loop, "timeout_seconds": 10}, outcome="more", semantic_attempt=0, progress_marker=None)

    def test_todo_selection_is_semantic_not_quota_or_lease(self):
        todos = [{"id": "done", "status": "completed"}, {"id": "b", "status": "ready", "priority": 1, "depends_on": ["done"]}, {"id": "a", "status": "ready", "priority": 2, "depends_on": ["done"]}]
        self.assertEqual(select_todo(todos)["id"], "a")
        text = (ROOT / "Orchestration/Graph/todo_selector.py").read_text(encoding="utf-8")
        self.assertNotIn("quota.", text)
        self.assertNotIn("lease_", text)

    def test_route_authority_migrated_from_context_index(self):
        catalog = load_routes(ROUTE_PATH)
        selected = select_route(fingerprint(), catalog)
        self.assertEqual(selected["route_id"], "csharp-local-fix")
        self.assertEqual(selected["profile"], "personal_full_control")
        incident = select_route(fingerprint(intent="investigate", artifact="shader", scope="multi_source", failure_mode="rendering_unknown", architecture_state="not_applicable", mutation_target="none", evidence_state="unknown"), catalog)
        self.assertEqual(incident["route_id"], "rendering-incident")
        context_catalog = yaml.safe_load((ROOT / "Context/Selection/context-catalog.yaml").read_text(encoding="utf-8"))
        self.assertEqual(context_catalog["route_authority"], "Orchestration/Routing")
        self.assertTrue(set(context_catalog["routes"]).issubset(set(catalog["routes"])))

    def test_state_mappings_validate_persistence_contracts(self):
        workflow = workflow_state_patch(run_id="run", parent_graph_id="development", active_subgraph_id="planning", active_node_id="select_route", updated_at="2026-08-29T00:00:00+00:00")
        workflow_schema = yaml.safe_load((ROOT / "Persistence/Contracts/workflow-state.schema.yaml").read_text(encoding="utf-8"))
        Draft202012Validator(workflow_schema).validate(workflow)
        loop = loop_control_state_patch(run_id="run", loop_id="investigation-evidence-loop", semantic_attempt=1, progress_marker="e1", decision="continue", updated_at="2026-08-29T00:00:00+00:00")
        loop_schema = yaml.safe_load((ROOT / "Persistence/Contracts/loop-control-state.schema.yaml").read_text(encoding="utf-8"))
        Draft202012Validator(loop_schema).validate(loop)

    def test_health_node_uses_runtime_port_without_implementing_probe(self):
        self.assertEqual(execute_health_check(FakeHealthPort("healthy"), {}, required=True)["consequence"], "continue")
        self.assertEqual(execute_health_check(FakeHealthPort("unavailable"), {}, required=True)["consequence"], "blocked")

    def test_orchestrator_emits_runtime_handoff_not_process_call(self):
        graph = load_graph(GRAPH_PATH)
        value = transition(graph=graph, run_id="run", current_node_id="plan_scope", signal="investigate", route_id="rendering-incident", execution_profile="personal_full_control", context_id="ctx", context_fingerprint="fp")
        self.assertEqual(value["decision"], "run_runtime")
        self.assertEqual(value["node_id"], "environment_check")
        self.assertEqual(value["runtime_handoff"]["action_id"], "rendering-incident:environment_check")
        schema = yaml.safe_load((ROOT / "Orchestration/Contracts/orchestration-decision.schema.yaml").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(value)

    def test_fast_path_bypasses_parent_graph_only_for_simple_bounded_task(self):
        direct = fast_path(run_id="run", route_id="csharp-local-fix", execution_profile="personal_full_control", context_id="ctx", context_fingerprint="fp", simple_task=True, requires_semantic_replan=False, runtime_action_id="execute_change")
        self.assertEqual(direct["decision"], "fast_path")
        self.assertIsNone(fast_path(run_id="run", route_id="rendering-incident", execution_profile="personal_full_control", context_id="ctx", context_fingerprint="fp", simple_task=False, requires_semantic_replan=True, runtime_action_id="inspect_sources"))

    def test_parallel_plan_never_combines_write_conflicts(self):
        groups = plan_parallel([{"id": "read-a", "parallel_safe": True, "write_set": []}, {"id": "read-b", "parallel_safe": True, "write_set": []}, {"id": "write-a", "parallel_safe": True, "write_set": ["A.cs"]}, {"id": "write-a-2", "parallel_safe": True, "write_set": ["A.cs"]}])
        self.assertEqual(groups[0], ["read-a", "read-b", "write-a"])
        self.assertEqual(groups[1], ["write-a-2"])

    def test_orchestration_contains_no_runtime_execution_implementation(self):
        forbidden = ("subprocess.", "os.kill", "taskkill", "run_streaming_process", "ExecutionLimitTracker", "snapshot_workspace", "evaluate_mutation_scope")
        for path in (ROOT / "Orchestration").rglob("*.py"):
            if path.name.startswith("test_"): continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{path}: {token}")


if __name__ == "__main__":
    unittest.main()