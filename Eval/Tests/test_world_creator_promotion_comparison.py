from __future__ import annotations

import copy
import unittest

from Eval.Regression.compare_world_planning_promotion import compare_world_planning
from Runtime.Tests.test_world_creator_entry_fixture import WorldCreatorEntryFixtureTests


class WorldCreatorPromotionComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = WorldCreatorEntryFixtureTests(methodName="test_dungeon_entry_to_providerless_world_plan")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        entry = fixture.entry(environment_type="dungeon", desired_mood="dark exploration")
        *_, manifest = fixture.prepare(entry)
        result = fixture.result(manifest, entry, [fixture.package("layout", "Define traversable zones", "generic_unity")], zones=["entrance", "chambers"])
        base = copy.deepcopy(manifest)
        base["materialized_context"]["specialist_context"] = None
        skill = copy.deepcopy(base)
        skill["materialized_context"]["selected_refs"]["skill"] = {"resolved_path": ".agents/skills/unity-architecture-design/SKILL.md"}
        review = {"goal_preservation": True, "plan_completeness": 3, "dependency_quality": 3, "open_decision_detection": 4, "domain_hint_quality": 3, "evidence_requirement_quality": 3, "hidden_decision_count": 0, "unnecessary_work_packages": 0, "token_usage": 1200, "trace_clarity": "clear"}
        self.arms = {"A_unity_agent": {"task_id": "dungeon", "run_kind": "fixture", "manifest": base, "result": {"world_plan": copy.deepcopy(result["world_plan"])}, "review": copy.deepcopy(review)}, "B_world_skill": {"task_id": "dungeon", "run_kind": "fixture", "manifest": skill, "result": {"world_plan": copy.deepcopy(result["world_plan"])}, "review": copy.deepcopy(review)}, "C_world_creator": {"task_id": "dungeon", "run_kind": "fixture", "manifest": manifest, "result": result, "review": copy.deepcopy(review)}}

    def test_providerless_comparison_records_reviews_without_winner(self) -> None:
        report = compare_world_planning(self.arms)
        self.assertTrue(report["candidate_contract_verified"])
        self.assertEqual(report["candidate_context_binding"], "verified")
        self.assertEqual(report["promotion_decision"], "requires_human_review")
        self.assertIsNone(report["winner"])
        self.assertEqual(report["runtime_evaluation"], "NOT_EVALUATED_RUNTIME")
        self.assertEqual(set(report["arms"]), set(self.arms))

    def test_missing_skill_stale_source_and_invalid_review_fail_closed(self) -> None:
        missing_skill = copy.deepcopy(self.arms)
        missing_skill["B_world_skill"]["manifest"]["materialized_context"]["selected_refs"]["skill"] = None
        with self.assertRaisesRegex(ValueError, "Skill"):
            compare_world_planning(missing_skill)
        stale = copy.deepcopy(self.arms)
        stale["C_world_creator"]["result"]["source_context_fingerprint"] = "sha256:stale"
        with self.assertRaisesRegex(ValueError, "source Context"):
            compare_world_planning(stale)
        invalid = copy.deepcopy(self.arms)
        invalid["C_world_creator"]["review"]["hidden_decision_count"] = -1
        with self.assertRaisesRegex(ValueError, "review metrics"):
            compare_world_planning(invalid)


if __name__ == "__main__":
    unittest.main()
