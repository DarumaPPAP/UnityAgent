"""Artist route expectations live with UnityAgent's semantic routing authority."""
from __future__ import annotations

from pathlib import Path
import unittest

from Orchestration.Routing.route_selector import load_routes, select_route


ROOT = Path(__file__).resolve().parents[2]


class ArtistRouteOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_routes(ROOT / "Orchestration/Routing/task-routes.yaml")

    def fingerprint(self, *, artifact: str, mutation_target: str) -> dict[str, str]:
        return {"intent": "design", "artifact": artifact, "scope": "project_asset", "failure_mode": "none", "architecture_state": "not_applicable", "mutation_target": mutation_target, "evidence_state": "known", "project_access": "authorized"}

    def test_visual_lookdev_selects_artist_route(self) -> None:
        route = select_route(self.fingerprint(artifact="visual", mutation_target="visual_plan"), self.catalog)

        self.assertEqual(route["route_id"], "artist-lookdev")
        self.assertEqual(self.catalog["routes"][route["route_id"]]["specialist_profile"], "artist_subagent")

    def test_cinematic_plan_selects_artist_route(self) -> None:
        route = select_route(self.fingerprint(artifact="cinematic", mutation_target="visual_plan"), self.catalog)

        self.assertEqual(route["route_id"], "artist-cinematic")
        self.assertEqual(self.catalog["routes"][route["route_id"]]["specialist_profile"], "artist_subagent")

    def test_compile_request_does_not_select_artist_route(self) -> None:
        route = select_route(self.fingerprint(artifact="project", mutation_target="source"), self.catalog)

        self.assertEqual(route["route_id"], "generic-planning")
        self.assertNotIn("specialist_profile", self.catalog["routes"][route["route_id"]])


if __name__ == "__main__":
    unittest.main()
