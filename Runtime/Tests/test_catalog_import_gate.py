from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import yaml

from Runtime.ReferenceImplementation.catalog_import_gate import CatalogImportError, build_import_plan
from Runtime.ReferenceImplementation.profiles import CATALOG, SubAgentProfileCatalog, runtime_profile_revision
from Runtime.ReferenceImplementation.runtime import reference_definition_fingerprint
from Tools.unity_agent_cli import _fingerprint


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "Runtime/ReferenceImplementation/subagent-catalog.yaml"
HUB_FIXTURE_PATH = ROOT / "Runtime/Tests/Fixtures/hub-artist-subagent-catalog-v1.1.yaml"


def _raw_catalog() -> dict:
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))


def _snapshot_bytes(value: dict) -> bytes:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=1000).encode("utf-8")


def _plan(value: dict, *, current_catalog: SubAgentProfileCatalog = CATALOG) -> dict:
    payload = _snapshot_bytes(value)
    current_bytes = (
        CATALOG_PATH.read_bytes()
        if current_catalog is CATALOG
        else _snapshot_bytes(current_catalog.to_mapping())
    )
    return build_import_plan(
        payload,
        source_ref="github://DarumaPPAP/UnitySubAgentHub/refs/heads/main/catalog.yaml",
        expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
        current_catalog=current_catalog,
        current_catalog_bytes=current_bytes,
        current_catalog_ref="Runtime/ReferenceImplementation/subagent-catalog.yaml",
    )


def _review_profile() -> dict:
    return {
        "profile_id": "review_subagent",
        "display_name": "ReviewSubAgent",
        "provider_id": "unity_cli",
        "audience": "review_subagent",
        "goal_type": "example.asset.review",
        "capabilities": ["example.asset.inspect", "example.asset.review"],
        "primary_capability": "example.asset.review",
        "required_evidence": ["state_observation", "review_capture"],
        "activation": {
            "install_mode": "optional",
            "auto_install": False,
            "required_environment": ["unity_cli.available"],
        },
        "scope": {
            "default_target_guid": "asset-guid-001",
            "component_type": "Example.Component",
            "property_paths": ["Example.value"],
            "mutation_channels": ["typed_property"],
            "max_targets": 1,
        },
        "value": {
            "type": "float",
            "unit": "normalized",
            "minimum": 0,
            "maximum": 100,
            "maximum_exclusive": True,
        },
        "approval": {
            "default_minimum": 10,
            "default_maximum": 90,
            "minimum_exclusive": True,
            "maximum_exclusive": True,
        },
        "evidence": {
            "source_type": "example_review",
            "producer": "UnityAgent.ExampleReview.v1",
            "provenance_token": "review_subagent",
        },
    }


class CatalogImportGateTests(unittest.TestCase):
    def test_current_catalog_snapshot_is_a_read_only_noop(self) -> None:
        plan = _plan(_raw_catalog())

        self.assertEqual(plan["status"], "no_op")
        self.assertEqual(plan["changes"][0]["classification"], "No-op")
        self.assertEqual(len(plan["source"]["sha256"].removeprefix("sha256:")), 64)
        self.assertFalse(plan["apply"]["catalog_write_performed"])
        self.assertFalse(plan["apply"]["requires_pull_request"])

    def test_current_hub_export_fixture_is_accepted_as_a_noop(self) -> None:
        payload = HUB_FIXTURE_PATH.read_bytes()
        plan = build_import_plan(
            payload,
            source_ref="github://DarumaPPAP/UnitySubAgentHub/refs/heads/main/export",
            expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
            current_catalog=CATALOG,
            current_catalog_bytes=CATALOG_PATH.read_bytes(),
            current_catalog_ref="Runtime/ReferenceImplementation/subagent-catalog.yaml",
        )

        self.assertEqual(plan["status"], "no_op")
        self.assertEqual(plan["source"]["sha256"], "sha256:" + hashlib.sha256(payload).hexdigest())

    def test_current_catalog_digest_is_bound_to_exact_bytes(self) -> None:
        payload = CATALOG_PATH.read_bytes()
        with self.assertRaises(CatalogImportError) as context:
            build_import_plan(
                payload,
                source_ref="test://current-digest",
                expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
                current_catalog=None,
                current_catalog_bytes=payload,
                current_catalog_sha256="sha256:" + "0" * 64,
            )

        self.assertEqual(context.exception.code, "current_catalog_digest_mismatch")

    def test_current_hub_producer_mismatch_is_blocked_without_normalization(self) -> None:
        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["evidence"]["producer"] = "UnityAgent.ReferenceImplementation.v1"

        plan = _plan(snapshot)

        self.assertEqual(plan["status"], "blocked")
        change = plan["changes"][0]
        self.assertEqual(change["classification"], "Changed")
        self.assertEqual(change["protected_fields_changed"], ["evidence.producer"])
        self.assertIn("evidence.producer", plan["blocking_reasons"][0])
        self.assertEqual(snapshot["profiles"]["artist_subagent"]["evidence"]["producer"], "UnityAgent.ReferenceImplementation.v1")

    def test_added_removed_changed_and_noop_are_reported(self) -> None:
        current = _raw_catalog()
        current["profiles"]["review_subagent"] = _review_profile()
        current_catalog = SubAgentProfileCatalog.from_mapping(current)

        added_snapshot = _raw_catalog()
        added_snapshot["profiles"]["review_subagent"] = _review_profile()
        added = _plan(added_snapshot)
        self.assertEqual({item["classification"] for item in added["changes"]}, {"No-op", "Added"})

        removed_snapshot = _raw_catalog()
        removed = _plan(removed_snapshot, current_catalog=current_catalog)
        removed_change = next(item for item in removed["changes"] if item["profile_id"] == "review_subagent")
        self.assertEqual(removed_change["classification"], "Removed")
        self.assertEqual(removed["status"], "blocked")

        changed_snapshot = _raw_catalog()
        changed_snapshot["profiles"]["artist_subagent"]["display_name"] = "ArtistSubAgent (renamed)"
        changed = _plan(changed_snapshot)
        changed_change = changed["changes"][0]
        self.assertEqual(changed_change["classification"], "Changed")
        self.assertEqual(changed_change["changed_fields"], ["display_name"])
        self.assertEqual(changed_change["risk"], "low")
        self.assertEqual(changed["status"], "requires_pull_request")

    def test_duplicate_capability_is_rejected_before_plan_creation(self) -> None:
        snapshot = _raw_catalog()
        profile = _review_profile()
        profile["capabilities"] = ["artist.camera.refine"]
        profile["primary_capability"] = "artist.camera.refine"
        snapshot["profiles"]["review_subagent"] = profile

        with self.assertRaises(CatalogImportError) as context:
            _plan(snapshot)

        self.assertEqual(context.exception.code, "duplicate_capability")

    def test_unknown_environment_fact_is_rejected(self) -> None:
        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["activation"]["required_environment"].append("unity_artist_cli.future_fact")

        with self.assertRaises(CatalogImportError) as context:
            _plan(snapshot)

        self.assertEqual(context.exception.code, "unknown_environment_fact")

    def test_unknown_provider_is_rejected(self) -> None:
        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["provider_id"] = "unknown_backend"

        with self.assertRaises(CatalogImportError) as context:
            _plan(snapshot)

        self.assertEqual(context.exception.code, "unknown_provider")

    def test_goal_type_must_be_declared_capability(self) -> None:
        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["goal_type"] = "artist.camera.other"

        with self.assertRaises(CatalogImportError) as context:
            _plan(snapshot)

        self.assertEqual(context.exception.code, "goal_capability_mismatch")

    def test_duplicate_yaml_key_and_unknown_catalog_field_are_rejected(self) -> None:
        payload = b"schema_version: '1.0'\nschema_version: '1.0'\ndefault_profile: artist_subagent\nprofiles: {}\n"
        with self.assertRaises(CatalogImportError) as duplicate:
            build_import_plan(
                payload,
                source_ref="test://duplicate-key",
                expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
                current_catalog=CATALOG,
            )
        self.assertEqual(duplicate.exception.code, "snapshot_syntax")

        snapshot = _raw_catalog()
        snapshot["unexpected"] = True
        with self.assertRaises(CatalogImportError) as unknown:
            _plan(snapshot)
        self.assertEqual(unknown.exception.code, "profile_validation")

    def test_identity_and_capability_shape_are_rejected(self) -> None:
        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["profile_id"] = "artist"
        with self.assertRaises(CatalogImportError) as identity:
            _plan(snapshot)
        self.assertEqual(identity.exception.code, "profile_validation")

        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["capabilities"] = ["artist-camera-refine"]
        snapshot["profiles"]["artist_subagent"]["primary_capability"] = "artist-camera-refine"
        with self.assertRaises(CatalogImportError) as capability:
            _plan(snapshot)
        self.assertEqual(capability.exception.code, "invalid_capability")

    def test_activation_scope_approval_and_evidence_shapes_are_rejected(self) -> None:
        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["activation"]["install_mode"] = "required"
        with self.assertRaises(CatalogImportError) as activation:
            _plan(snapshot)
        self.assertEqual(activation.exception.code, "profile_validation")

        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["scope"]["max_targets"] = True
        with self.assertRaises(CatalogImportError) as scope:
            _plan(snapshot)
        self.assertEqual(scope.exception.code, "profile_validation")

        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["approval"]["default_maximum"] = 181
        with self.assertRaises(CatalogImportError) as approval:
            _plan(snapshot)
        self.assertEqual(approval.exception.code, "approval_outside_value")

        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["evidence"]["unexpected"] = "value"
        with self.assertRaises(CatalogImportError) as evidence:
            _plan(snapshot)
        self.assertEqual(evidence.exception.code, "profile_validation")

    def test_non_finite_and_exclusive_boundary_numbers_are_rejected(self) -> None:
        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["value"]["maximum"] = float("nan")
        with self.assertRaises(CatalogImportError) as non_finite:
            _plan(snapshot)
        self.assertEqual(non_finite.exception.code, "profile_validation")

        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["approval"]["default_maximum"] = 180
        with self.assertRaises(CatalogImportError) as boundary:
            _plan(snapshot)
        self.assertEqual(boundary.exception.code, "approval_outside_value")

        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["value"]["minimum"] = 10**1000
        with self.assertRaises(CatalogImportError) as huge:
            _plan(snapshot)
        self.assertEqual(huge.exception.code, "profile_validation")

    def test_strict_boolean_type_is_rejected(self) -> None:
        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["activation"]["auto_install"] = "false"
        payload = _snapshot_bytes(snapshot)

        with self.assertRaises(CatalogImportError) as context:
            build_import_plan(
                payload,
                source_ref="test://strict-types",
                expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
                current_catalog=CATALOG,
            )

        self.assertEqual(context.exception.code, "profile_validation")

    def test_tampered_snapshot_is_rejected_before_semantic_processing(self) -> None:
        payload = _snapshot_bytes(_raw_catalog())
        before = json.dumps(_raw_catalog(), sort_keys=True)

        with self.assertRaises(CatalogImportError) as context:
            build_import_plan(
                payload,
                source_ref="test://tamper",
                expected_sha256="sha256:" + "0" * 64,
                current_catalog=CATALOG,
            )

        self.assertEqual(context.exception.code, "snapshot_digest_mismatch")
        self.assertEqual(json.dumps(_raw_catalog(), sort_keys=True), before)

    def test_protected_change_and_invalid_input_never_mutate_runtime_catalog(self) -> None:
        before = CATALOG.to_mapping()
        snapshot = _raw_catalog()
        snapshot["profiles"]["artist_subagent"]["scope"]["max_targets"] = 2

        plan = _plan(snapshot)

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(CATALOG.to_mapping(), before)
        self.assertEqual(CATALOG.get("artist_subagent").scope["max_targets"], 1)

        invalid = _raw_catalog()
        invalid["profiles"]["artist_subagent"]["capabilities"].append("artist.camera.refine")
        with self.assertRaises(CatalogImportError):
            _plan(invalid)
        self.assertEqual(CATALOG.to_mapping(), before)

    def test_runtime_eligibility_remains_current_environment_owned(self) -> None:
        plan = _plan(_raw_catalog())
        self.assertEqual(plan["status"], "no_op")

        profile = CATALOG.get("artist_subagent")
        for compatible, expected in ((False, "unavailable"), ("unknown", "unknown")):
            snapshot = {
                "unity_artist_cli": {
                    "available": True,
                    "compatible": compatible,
                    "project_bound": True,
                    "package_installed": True,
                    "pipeline_reachable": True,
                }
            }
            failure = profile.eligibility_failure(snapshot)
            self.assertIsNotNone(failure)
            self.assertEqual(failure[0], expected)

    def test_runtime_profile_revision_changes_for_catalog_and_provider_registry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Runtime/ReferenceImplementation").mkdir(parents=True)
            (root / "Runtime/Tooling").mkdir(parents=True)
            provider_path = root / "Runtime/Tooling/provider_registry.yaml"
            catalog_path = root / "Runtime/ReferenceImplementation/subagent-catalog.yaml"
            provider_path.write_text("provider-a\n", encoding="utf-8")
            catalog_path.write_text("catalog-a\n", encoding="utf-8")

            with mock.patch("Tools.unity_agent_cli.ROOT", root):
                first = _fingerprint()["runtime_profile_revision"]
                catalog_path.write_text("catalog-b\n", encoding="utf-8")
                second = _fingerprint()["runtime_profile_revision"]
                provider_path.write_text("provider-b\n", encoding="utf-8")
                third = _fingerprint()["runtime_profile_revision"]

        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)

    def test_reference_evidence_fingerprint_uses_the_same_catalog_revision(self) -> None:
        fingerprint = reference_definition_fingerprint()

        self.assertEqual(fingerprint["runtime_profile_revision"], runtime_profile_revision())


if __name__ == "__main__":
    unittest.main()
