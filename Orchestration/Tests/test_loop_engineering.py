from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Orchestration.Loop.semantic_loop import decide_semantic_loop, validate_loop_definition
from Orchestration.Loop.todo_selector import select_todo

GRAPH_PATH = ROOT / "Orchestration/Definitions/development-parent-graph.yaml"
DECISION_SCHEMA_PATH = ROOT / "Orchestration/Contracts/semantic-loop-decision.schema.yaml"


class LoopEngineeringTests(unittest.TestCase):
    def test_all_declared_loops_are_deterministic(self):
        graph = yaml.safe_load(GRAPH_PATH.read_text(encoding="utf-8")) or {}
        for loop in graph.get("local_loops") or []:
            validate_loop_definition(loop)
            sets = [set(loop.get(name) or []) for name in ("continue_on", "replan_on", "exit_on")]
            self.assertFalse(sets[0] & sets[1], loop["id"])
            self.assertFalse(sets[0] & sets[2], loop["id"])
            self.assertFalse(sets[1] & sets[2], loop["id"])

    def test_semantic_decision_matches_contract(self):
        loop = {
            "id": "investigation-evidence-loop",
            "continue_on": ["more"],
            "replan_on": ["invalid"],
            "exit_on": ["done"],
        }
        value = decide_semantic_loop(
            loop,
            outcome="more",
            semantic_attempt=2,
            progress_marker="evidence-3",
        )
        schema = yaml.safe_load(DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(value)
        self.assertEqual(value["decision"], "continue")
        self.assertEqual(value["semantic_attempt"], 3)

    def test_unknown_outcome_fails_closed(self):
        loop = {
            "id": "fixture-loop",
            "continue_on": ["more"],
            "replan_on": ["invalid"],
            "exit_on": ["done"],
        }
        value = decide_semantic_loop(
            loop,
            outcome="mystery",
            semantic_attempt=0,
            progress_marker=None,
        )
        self.assertEqual(value["decision"], "blocked")
        self.assertEqual(value["semantic_attempt"], 0)

    def test_no_progress_converts_continue_to_replan(self):
        loop = {
            "id": "fixture-loop",
            "continue_on": ["more"],
            "replan_on": [],
            "exit_on": ["done"],
        }
        value = decide_semantic_loop(
            loop,
            outcome="more",
            semantic_attempt=1,
            progress_marker="same",
            progress_made=False,
        )
        self.assertEqual(value["decision"], "replan")
        self.assertIsNotNone(value["replan_reason"])

    def test_overlapping_outcomes_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_loop_definition(
                {
                    "id": "bad-loop",
                    "continue_on": ["again"],
                    "replan_on": ["again"],
                    "exit_on": [],
                }
            )

    def test_runtime_control_fields_are_rejected(self):
        for key in (
            "timeout_seconds",
            "hard_retry_ceiling",
            "maximum_retry_attempts",
            "max_turns",
            "cost_ceiling",
            "quota",
            "lease",
            "retry_budget",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_loop_definition(
                    {
                        "id": "bad-loop",
                        "continue_on": [],
                        "replan_on": [],
                        "exit_on": [],
                        key: 1,
                    }
                )

    def test_todo_selector_rejects_ambiguous_or_broken_dependencies(self):
        with self.assertRaises(ValueError):
            select_todo([{"id": "a"}, {"id": "a"}])
        with self.assertRaises(ValueError):
            select_todo([{"id": "a", "depends_on": ["missing"]}])

    def test_graph_package_no_longer_owns_loop_decision_code(self):
        self.assertFalse((ROOT / "Orchestration/Graph/local_loop.py").exists())
        self.assertFalse((ROOT / "Orchestration/Graph/todo_selector.py").exists())
        graph_state = (ROOT / "Orchestration/Graph/state_mapping.py").read_text(encoding="utf-8")
        self.assertNotIn("loop_control_state_patch", graph_state)

    def test_loop_package_has_no_runtime_or_persistence_execution_authority(self):
        forbidden = (
            "from Runtime",
            "import Runtime",
            "subprocess.",
            "os.kill",
            "taskkill",
            "maximum_retry_attempts =",
            "Persistence.",
            "write_text(",
            "open(",
        )
        for path in (ROOT / "Orchestration/Loop").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{path}: {token}")

    def test_runtime_fallback_remains_infrastructure_only(self):
        runtime = (ROOT / "Runtime/Tooling/fallback_policy.py").read_text(encoding="utf-8")
        self.assertIn("Infrastructure-only fallback policy", runtime)
        self.assertIn("no semantic replan", runtime)
        self.assertNotIn("Orchestration.Loop", runtime)
        self.assertNotIn("decide_semantic_loop", runtime)

    def test_no_production_continuation_controller_returns(self):
        for root_name in ("Orchestration", "Runtime", "Persistence", "Operations"):
            for path in (ROOT / root_name).rglob("*.py"):
                if path.name.startswith("test_"):
                    continue
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("class ContinuationController", text, str(path))
                self.assertNotIn("from Tools.ContinuationController", text, str(path))


if __name__ == "__main__":
    unittest.main()
