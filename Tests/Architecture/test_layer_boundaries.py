from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Tools.LayerBoundaryValidator.validate_layer_boundaries import EXPECTED_EDGES, EXPECTED_LAYERS, validate


class LayerBoundaryTests(unittest.TestCase):
    def test_canonical_five_layer_contract_is_valid(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_contract_has_no_entry_to_provider_edge(self) -> None:
        contract = yaml.safe_load((ROOT / "Specs/unityagent-layer-contract.yaml").read_text(encoding="utf-8"))
        edges = {
            (item["from"], item["to"], item["mode"])
            for item in contract["dependency_graph"]
        }
        self.assertEqual(set(contract["layers"]), EXPECTED_LAYERS)
        self.assertEqual(edges, EXPECTED_EDGES)
        self.assertNotIn(("entry", "provider_layer", "direct"), edges)

    def test_entry_request_rejects_provider_identity(self) -> None:
        from ControlPlane.unity_agent_control_plane import validate_entry_request

        request = {
            "schema_version": "1.0",
            "request_id": "entry-1",
            "entry_point": "codex_plugin",
            "project_root": str(ROOT),
            "intent": {"kind": "inspect"},
            "route_id": "inspect_project",
            "execution_profile": "generic_planning",
            "context_id": "context-1",
            "context_fingerprint": "context-hash",
            "task_contract_runtime_projection": {},
            "mutation_scope": {},
            "validation_requirements": [],
            "capability_requests": [{"provider_ref": "unity_cli"}],
        }
        with self.assertRaisesRegex(ValueError, "Provider identity"):
            validate_entry_request(request)


if __name__ == "__main__":
    unittest.main()
