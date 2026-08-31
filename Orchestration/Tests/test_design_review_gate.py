from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Orchestration.Orchestrator.orchestrator import fast_path, load_graph, transition
from Orchestration.Routing.route_selector import load_routes, select_route

GRAPH_PATH = ROOT / "Orchestration/Definitions/development-parent-graph.yaml"
ROUTE_PATH = ROOT / "Orchestration/Routing/task-routes.yaml"
DESIGN_SCHEMA_PATH = ROOT / "Orchestration/Contracts/design-review-artifact.schema.yaml"


def fingerprint(**overrides):
    base = {
        "intent": "design",
        "artifact": "architecture",
        "scope": "cross_system",
        "failure_mode": "none",
        "architecture_state": "undecided",
        "mutation_target": "source",
        "evidence_state": "known",
        "project_access": "authorized",
    }
    base.update(overrides)
    return base


class DesignReviewGateTests(unittest.TestCase):
    def test_design_routes_require_review_but_local_fix_does_not(self):
        catalog = load_routes(ROUTE_PATH)

        architecture = select_route(fingerprint(), catalog)
        self.assertEqual(architecture["route_id"], "architecture-design")
        self.assertEqual(architecture["design_review"], "required")

        local_fix = select_route(
            fingerprint(
                intent="fix",
                artifact="csharp",
                scope="local",
                failure_mode="runtime",
                architecture_state="decided",
                mutation_target="source",
            ),
            catalog,
        )
        self.assertEqual(local_fix["route_id"], "csharp-local-fix")
        self.assertEqual(local_fix["design_review"], "not_required")

    def test_parent_graph_contains_human_design_review_gate(self):
        graph = load_graph(GRAPH_PATH)
        schema = yaml.safe_load(
            (ROOT / "Orchestration/Contracts/graph-definition.schema.yaml").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(graph)

        subgraphs = {item["id"]: item for item in graph["subgraphs"]}
        self.assertIn("design_review", subgraphs)
        self.assertEqual(subgraphs["design_review"]["entry_node_id"], "compose_design_preview")

        gates = {item["id"]: item for item in graph["gates"]}
        self.assertEqual(gates["design_review_gate"]["node_id"], "await_design_approval")
        self.assertEqual(gates["design_review_gate"]["source"], "human")

    def test_design_review_can_revise_or_continue_to_implementation(self):
        graph = load_graph(GRAPH_PATH)
        common = {
            "graph": graph,
            "run_id": "run",
            "route_id": "architecture-design",
            "execution_profile": "personal_full_control",
            "context_id": "ctx",
            "context_fingerprint": "fp",
        }

        preview = transition(current_node_id="plan_scope", signal="design_review", **common)
        self.assertEqual(preview["subgraph_id"], "design_review")
        self.assertEqual(preview["node_id"], "compose_design_preview")

        present = transition(current_node_id="compose_design_preview", signal="preview_ready", **common)
        self.assertEqual(present["node_id"], "present_design_preview")

        approval = transition(current_node_id="present_design_preview", signal="presented", **common)
        self.assertEqual(approval["node_id"], "await_design_approval")

        revise = transition(current_node_id="await_design_approval", signal="revision_requested", **common)
        self.assertEqual(revise["node_id"], "compose_design_preview")

        approved = transition(current_node_id="await_design_approval", signal="approved_implement", **common)
        self.assertEqual(approved["node_id"], "mutation_precheck")

    def test_fast_path_cannot_bypass_required_or_conditional_design_review(self):
        common = {
            "run_id": "run",
            "route_id": "architecture-design",
            "execution_profile": "personal_full_control",
            "context_id": "ctx",
            "context_fingerprint": "fp",
            "simple_task": True,
            "requires_semantic_replan": False,
            "runtime_action_id": "execute_change",
        }
        self.assertIsNone(fast_path(design_review_requirement="required", **common))
        self.assertIsNone(fast_path(design_review_requirement="conditional", **common))
        self.assertIsNotNone(fast_path(design_review_requirement="not_required", **common))

    def test_design_review_artifact_contract_accepts_expected_output(self):
        schema = yaml.safe_load(DESIGN_SCHEMA_PATH.read_text(encoding="utf-8"))
        artifact = {
            "schema_version": "1.0",
            "kind": "design_review",
            "goal": "Build a Unity editor tool",
            "route": {
                "route_id": "portable-feature",
                "design_review_requirement": "required",
                "intended_action": "implement",
            },
            "execution_graph": {
                "mermaid": "flowchart LR\nA-->B",
                "stages": [{"id": "design_review", "purpose": "confirm design", "owner": "orchestration"}],
            },
            "checklist": [{"id": "goal", "item": "Goal matches design", "status": "confirmed", "note": ""}],
            "final_image_spec": {
                "summary": "A usable editor tool with a bounded workflow.",
                "user_visible_behavior": ["User can run the tool from the Editor."],
                "major_components": ["EditorWindow", "Feature logic"],
                "data_or_control_flow": ["User action -> feature logic -> result"],
                "acceptance_criteria": ["The requested workflow completes without unrelated mutation."],
                "non_goals": ["No speculative runtime service."],
                "unresolved": [],
            },
            "approval": {
                "status": "pending",
                "allowed_decisions": ["approve", "revise", "reject"],
            },
        }
        Draft202012Validator(schema).validate(artifact)


if __name__ == "__main__":
    unittest.main()
