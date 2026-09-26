"""Specialist Pilot前に、既存RouteのArtist / Graphics / Performance境界を固定する。"""
from __future__ import annotations

from pathlib import Path
import unittest

from Orchestration.Routing.route_selector import load_routes, select_route


ROOT = Path(__file__).resolve().parents[2]


class SpecialistBoundaryPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routes = load_routes(ROOT / "Orchestration/Routing/task-routes.yaml")

    def route(self, **overrides: str) -> str:
        fingerprint = {"intent": "investigate", "artifact": "renderer_feature", "scope": "local", "failure_mode": "rendering_unknown", "architecture_state": "decided", "mutation_target": "none", "evidence_state": "unknown", "project_access": "authorized"}
        fingerprint.update(overrides)
        return select_route(fingerprint, self.routes)["route_id"]

    def test_outline_appearance_belongs_to_artist(self) -> None:
        route_id = self.route(intent="design", artifact="visual", scope="project_asset", failure_mode="visual", mutation_target="visual_plan", evidence_state="known")

        self.assertEqual(route_id, "artist-lookdev")
        self.assertEqual(self.routes["routes"][route_id]["specialist_profile"], "artist_subagent")

    def test_render_pass_failure_uses_existing_rendering_incident_route(self) -> None:
        self.assertEqual(self.route(), "rendering-incident")

    def test_render_pass_cost_belongs_to_performance_experiment(self) -> None:
        route_id = self.route(artifact="performance", failure_mode="performance", evidence_state="baseline_required")

        self.assertEqual(route_id, "performance-experiment")

    def test_known_shader_compile_failure_uses_shader_change(self) -> None:
        route_id = self.route(intent="fix", artifact="shader", failure_mode="compile", mutation_target="shader_source", evidence_state="known")

        self.assertEqual(route_id, "shader-change")


if __name__ == "__main__":
    unittest.main()
