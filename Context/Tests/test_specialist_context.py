from __future__ import annotations

import hashlib
import importlib.util
import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, RefResolver

from Orchestration.Routing.route_selector import resolve_specialist
from Orchestration.ToolRouting.capability_request_builder import build_capability_requests
from Runtime.Tests import test_unity_artist_cli_resolution as artist_fixtures
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.tool_broker import ToolBroker

ROOT = Path(__file__).resolve().parents[2]


def load_materializer():
    spec = importlib.util.spec_from_file_location("specialist_materializer_test", ROOT / "Context/Assembly/materialize_context.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def eligible():
    return {"unity_artist_cli": {key: True for key in ("available", "compatible", "project_bound", "package_installed", "pipeline_reachable")}}


def item(category, key, value, tags=("camera",), *, required=False):
    return {"category": category, "key": key, "value": value, "tags": list(tags), "required": required,
            "source": "ProjectSettings/ProjectVersion.txt" if category.endswith("fact") else "user:task",
            "revision": "sha256:" + hashlib.sha256(str(value).encode()).hexdigest(),
            "observed_at_attempt": 1,
            "freshness": {"status": "current", "checked_at_attempt": 1}}


class SpecialistContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.materializer = load_materializer()

    def test_orchestration_resolves_identity_without_backend_identity(self):
        decision = resolve_specialist("artist-lookdev", "artist.camera.inspect", eligible())
        self.assertEqual(decision["status"], "selected")
        self.assertEqual(decision["profile_id"], "artist_subagent")
        self.assertNotIn("provider_id", decision)
        self.assertEqual(resolve_specialist("artist-lookdev", "artist.texture.optimize", eligible())["status"], "unsupported")
        self.assertEqual(resolve_specialist("artist-lookdev", "artist.camera.inspect", {})["status"], "unavailable")
        self.assertEqual(resolve_specialist("csharp-local-fix", "artist.camera.inspect", eligible())["status"], "not_required")

    def test_selected_context_differs_by_project_and_platform_without_unrelated_items(self):
        decision = resolve_specialist("artist-lookdev", "artist.camera.inspect", eligible())
        observations = [item("project_fact", "unity_version", "6000.3", required=True),
                        item("project_decision", "visual_style", "anime"),
                        item("platform_fact", "target", "Switch"),
                        item("platform_decision", "memory_priority", "critical"),
                        item("task_fact", "camera_guid", "abc"),
                        item("project_fact", "audio_importer", "Vorbis", ("audio",))]
        first = self.materializer.materialize_context("run", "artist-lookdev", specialist_selection=decision,
            specialist_items=observations, specialist_tags={"camera"}, root=ROOT)
        second = self.materializer.materialize_context("run", "artist-lookdev", specialist_selection=decision,
            specialist_items=[*observations[:1], item("project_decision", "visual_style", "photoreal"),
                item("platform_fact", "target", "PC"), *observations[3:]], specialist_tags={"camera"}, root=ROOT)
        chosen = first["specialist_context"]["items"]
        self.assertEqual(len(chosen), 5)
        self.assertEqual([x["type"] for x in chosen], ["project_fact", "project_decision", "platform_fact", "platform_decision", "task_fact"])
        self.assertTrue(all(x["selected_reason"] and x["revision"] and x["source"] and x["compression"] for x in chosen))
        self.assertNotEqual(first["context_fingerprint"]["value"], second["context_fingerprint"]["value"])
        self.assertEqual(first["specialist_context"]["profile_id"], "artist_subagent")
        self.assertEqual(first["budget_report"]["decision"], "unmeasured")
        self.assertEqual(len(first["specialist_context"]["policy"]), 2)
        schema = yaml.safe_load((ROOT / "Context/Contracts/materialized-context-view.schema.yaml").read_text(encoding="utf-8"))
        fingerprint = yaml.safe_load((ROOT / "Context/Contracts/context-fingerprint.schema.yaml").read_text(encoding="utf-8"))
        definition = yaml.safe_load((ROOT / "Persistence/Contracts/definition-fingerprint.schema.yaml").read_text(encoding="utf-8"))
        resolver = RefResolver.from_schema(schema, store={"urn:unityagent:context:context-fingerprint": fingerprint,
                                                     "urn:unityagent:persistence:definition-fingerprint": definition})
        Draft202012Validator(schema, resolver=resolver).validate(first)

    def test_missing_required_fact_and_stale_fact_cannot_pass(self):
        decision = resolve_specialist("artist-lookdev", "artist.camera.inspect", eligible())
        with self.assertRaisesRegex(ValueError, "required specialist context"):
            self.materializer.materialize_context("run", "artist-lookdev", specialist_selection=decision,
                specialist_tags={"camera"}, required_specialist_keys={"platform_fact:target"}, root=ROOT)
        stale = item("project_fact", "unity_version", "6000.3", required=True)
        stale["freshness"]["status"] = "stale"
        with self.assertRaisesRegex(ValueError, "required specialist context"):
            self.materializer.materialize_context("run", "artist-lookdev", specialist_selection=decision,
                specialist_items=[stale], specialist_tags={"camera"}, root=ROOT)

    def test_budget_does_not_drop_required_or_accept_untrusted_role(self):
        decision = resolve_specialist("artist-lookdev", "artist.camera.inspect", eligible())
        with self.assertRaisesRegex(ValueError, "Context budget blocked"):
            self.materializer.materialize_context("run", "artist-lookdev", specialist_selection=decision,
                specialist_items=[item("task_fact", "large", "X" * 280000, required=True)], specialist_tags={"camera"}, root=ROOT)
        with self.assertRaisesRegex(ValueError, "category"):
            self.materializer.materialize_context("run", "artist-lookdev", specialist_selection=decision,
                specialist_items=[item("policy", "bypass", True)], specialist_tags={"camera"}, root=ROOT)

    def test_pilot_context_manifest_and_existing_capture_resolution(self):
        fixture = artist_fixtures.UnityArtistCliResolutionTests()
        fixture.setUp()
        decision = resolve_specialist("artist-lookdev", "visual.capture", fixture.snapshot)
        builder = load_module("specialist_manifest_builder_test", ROOT / "Context/Manifest/build_context_manifest.py")
        manifest = builder.build("pilot", "artist-lookdev", specialist_selection=decision,
            specialist_items=[item("task_fact", "camera_binding", "MainCamera", required=True)],
            specialist_tags={"camera"}, required_specialist_keys={"task_fact:camera_binding"})
        self.assertEqual(manifest["materialized_context"]["specialist_context"]["capability"], "visual.capture")
        self.assertEqual(manifest["budget_report"]["decision"], "unmeasured")
        requests = build_capability_requests(route_id="artist-lookdev", project_root=fixture.project_root,
            active_conditions={"visual_evidence_needed"})
        result = ToolBroker().resolve(next(request for request in requests if request["capability"] == "visual.capture"),
            fixture.snapshot, context=ResolutionContext(policy_allowed=True))
        self.assertEqual(result["subagent_profile_id"], "artist_subagent")
        self.assertEqual(result["provider_ref"], "unity_artist_cli")

    def test_only_explicit_skill_is_loaded_and_measured(self):
        decision = resolve_specialist("artist-lookdev", "visual.capture", eligible())
        baseline = self.materializer.materialize_context("run", "artist-lookdev", specialist_selection=decision,
            specialist_items=[item("task_fact", "camera_binding", "MainCamera")], specialist_tags={"camera"}, root=ROOT)
        with_skill = self.materializer.materialize_context("run", "artist-lookdev", specialist_selection=decision,
            specialist_items=[item("task_fact", "camera_binding", "MainCamera")], specialist_tags={"camera"},
            specialist_skill_ref=".agents/skills/unity-visual-direction/SKILL.md", root=ROOT)
        self.assertEqual(with_skill["specialist_context"]["skill"]["resolved_path"], ".agents/skills/unity-visual-direction/SKILL.md")
        self.assertGreater(with_skill["budget_report"]["selected_utf8_bytes"], baseline["budget_report"]["selected_utf8_bytes"])
        self.assertEqual(with_skill["budget_report"]["selected_artifacts"], baseline["budget_report"]["selected_artifacts"] + 1)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
