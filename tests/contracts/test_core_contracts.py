"""既存Validatorによる契約違反の検出と、Entryの権限境界を確認する。"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml
from jsonschema import ValidationError

from tools.layer_boundary_validator import validate_layer_boundaries as layers
from tools.policy_validator import validate_user_policy_integrity as policy
from unityagent.control_plane.unity_agent_control_plane import validate_entry_request

ROOT = Path(__file__).resolve().parents[2]


class CoreContractTests(unittest.TestCase):
    def test_layer_validator_detects_forbidden_dependencies(self):
        canonical = yaml.safe_load((ROOT / layers.CONTRACT_PATH).read_text(encoding="utf-8"))
        for violation, expected in (
            ("direct_edge", "dependency_graph does not match"),
            ("entry_permission", "Entry Layer must forbid"),
            ("control_plane_permission", "Control Plane must forbid"),
            ("invariant", "invariant must be true: no_entry_to_provider"),
        ):
            with self.subTest(violation=violation):
                contract = copy.deepcopy(canonical)
                if violation == "direct_edge":
                    contract["dependency_graph"].append({"from": "entry", "to": "provider_layer", "mode": "direct"})
                elif violation == "entry_permission":
                    contract["layers"]["entry"]["forbidden_dependencies"].remove("provider_layer")
                elif violation == "control_plane_permission":
                    contract["layers"]["control_plane"]["forbidden_dependencies"].remove("provider_layer_direct")
                else:
                    contract["invariants"]["no_entry_to_provider"] = False
                with patch.object(layers, "_load", return_value=contract):
                    errors = layers.validate(ROOT)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_policy_validator_detects_weakened_user_authority(self):
        relative = Path("src/unityagent/policy/user/user-policy.yaml")
        canonical = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / relative
            path.parent.mkdir(parents=True)
            risk = root / "src/unityagent/policy/risk/risk-levels.yaml"
            risk.parent.mkdir(parents=True)
            risk.write_bytes((ROOT / risk.relative_to(root)).read_bytes())
            for violation, expected in (
                ("owner", "policy_owner must be user"),
                ("approval", "protected user policy rule missing or weakened"),
                ("core", "protected core user policy missing"),
            ):
                with self.subTest(violation=violation):
                    value = copy.deepcopy(canonical)
                    if violation == "owner":
                        value["policy_owner"] = "external"
                    elif violation == "approval":
                        value["rules"]["policy_deletion_requires_explicit_user_approval"] = False
                    else:
                        del value["core_user_policies"]["engineering_principles"]
                    path.write_text(yaml.safe_dump(value), encoding="utf-8")
                    errors = policy.validate(root)
                    self.assertTrue(any(expected in error for error in errors), errors)

    def test_entry_schema_rejects_missing_required_fields(self):
        request = {
            "schema_version": "2.0",
            "request_id": "contract-test",
            "entry_point": "codex_plugin",
            "project_root": str(ROOT),
            "intent": {"kind": "project_inspection"},
        }
        validate_entry_request(request, root=ROOT)
        for field in ("request_id", "project_root", "intent"):
            with self.subTest(field=field):
                invalid = {key: value for key, value in request.items() if key != field}
                with self.assertRaisesRegex(ValidationError, field):
                    validate_entry_request(invalid, root=ROOT)

    def test_setup_skill_points_to_current_control_plane_bootstrap(self) -> None:
        skill = (ROOT / ".agents/plugins/unity-agent/skills/unity-agent-setup/SKILL.md").read_text(encoding="utf-8")
        installer = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
        url = "https://raw.githubusercontent.com/DarumaPPAP/UnityAgent/main/scripts/install.ps1"
        self.assertIn(url, skill)
        self.assertIn(url, installer)
        self.assertIn("UNITY_AGENT_TAG", skill)
        self.assertNotIn("migration/unity-artist-cli-v2", skill)
        self.assertNotIn("UNITY_AGENT_REF", skill)

    def test_canonical_ci_runs_for_all_pull_requests_and_main_pushes(self) -> None:
        workflow = yaml.load(
            (ROOT / ".github/workflows/validate-agent-contracts.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        triggers = workflow["on"]
        self.assertIn("pull_request", triggers)
        # PR本文編集はPR Qualityのみで検証する。Canonical CIは変更があるPRとmainで実行。
        pr_triggers = triggers["pull_request"]
        self.assertIsInstance(pr_triggers, dict)
        self.assertTrue(
            {"opened", "synchronize", "reopened", "ready_for_review"}
            <= set(pr_triggers["types"])
        )
        self.assertNotIn("edited", pr_triggers["types"])
        self.assertNotIn("paths", pr_triggers)
        self.assertEqual(triggers["push"]["branches"], ["main"])
        self.assertNotIn("paths", triggers["push"])

    def test_entry_request_rejects_provider_identity(self) -> None:
        from unityagent.control_plane.unity_agent_control_plane import validate_entry_request

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

    def test_capability_and_mcp_runtime_authorities_remain_split(self):
        capability_context = yaml.safe_load(
            (ROOT / "src/unityagent/context/selection/tool-capability-catalog.yaml").read_text(encoding="utf-8")
        )
        runtime = yaml.safe_load((ROOT / "src/unityagent/runtime/permissions/mcp-activation.yaml").read_text(encoding="utf-8"))
        trust = yaml.safe_load((ROOT / "src/unityagent/policy/security/tool-trust.yaml").read_text(encoding="utf-8"))
        permissions = yaml.safe_load((ROOT / "src/unityagent/policy/security/permissions.yaml").read_text(encoding="utf-8"))
        ownership = yaml.safe_load((ROOT / "src/unityagent/policy/contracts/repository-ownership.yaml").read_text(encoding="utf-8"))
        self.assertEqual(capability_context["authority"], "Context")
        self.assertTrue(capability_context["rules"]["context_does_not_select_provider"])
        self.assertFalse((ROOT / "src/unityagent/context/selection/mcp-selection.yaml").exists())
        for level in ("level_2", "level_3", "level_4", "level_5"):
            self.assertIn(level, runtime["tool_exposure"])
        self.assertIn("source_read_policy", trust)
        self.assertEqual(
            permissions["requirements"]["mutate"]["requires"],
            ["approved_plan", "explicit_mutation_permission", "revision", "diff", "undo_path"],
        )
        self.assertEqual(
            permissions["requirements"]["bake"]["requires"],
            ["separate_explicit_bake_permission", "dependency_invalidation"],
        )
        self.assertEqual(ownership["repositories"]["policy"], "DarumaPPAP/UnityAgent")
        self.assertEqual(ownership["repositories"]["mcp"], "DarumaPPAP/MyUnityMCP")
