from dataclasses import replace
import unittest
from unittest.mock import patch

from tests.runtime import test_artist_command_adapter as boundary_fixture
from unityagent.runtime.tooling.providers.unity_cli.command_builder import build_pipeline_catalog_command


class ArtistProcessBindingTests(unittest.TestCase):
    def setUp(self):
        self.boundary = boundary_fixture.ArtistProviderBoundaryTests()
        self.boundary.setUp()
        self.addCleanup(self.boundary.doCleanups)
        self.boundary.discovery = replace(self.boundary.discovery, editor_status={"instances": []})

    def test_headless_editor_uses_measured_process_binding_and_artist_project_proof(self):
        result = self.boundary.run_command()
        self.assertEqual(result["status"], "passed", result)

    def test_missing_ambiguous_and_wrong_version_process_binding_never_dispatch(self):
        editor = self.boundary.snapshot["unity_editor"]
        for key, value in (("binding_status", "ambiguous_binding"), ("bound_instance_id", None), ("version", None), ("version", "2022.3.22f1")):
            previous = editor[key]
            editor[key] = value
            with self.subTest(key=key, value=value):
                self.assertEqual(self.boundary.run_command()["status"], "failed")
            editor[key] = previous
        self.assertEqual(self.boundary.calls, [])

    def test_explicit_foreign_editor_listing_cannot_be_overridden_by_process_binding(self):
        self.boundary.discovery = replace(self.boundary.discovery, editor_status={"instances": [{"projectPath": str(self.boundary.root / "other"), "state": "ready", "version": "6000.3.12f1"}]})
        self.assertEqual(self.boundary.run_command()["status"], "failed")
        self.assertEqual(self.boundary.calls, [])

    def test_broker_executor_preserves_cancel_event_and_timeout_type(self):
        event = object()
        with patch.object(self.boundary.provider, "run_artist", return_value={"status": "failed"}) as execute:
            self.boundary.provider.execute(self.boundary.request, arguments={"artist_command": boundary_fixture.ArtistCommand("inspect"), "cancel_event": event, "timeout_seconds": True})
        self.assertIs(execute.call_args.kwargs["cancel_event"], event)
        self.assertIs(execute.call_args.kwargs["timeout_seconds"], True)

    def test_catalog_explicitly_requests_commands_instead_of_beta14_default_tags(self):
        argv = build_pipeline_catalog_command("unity", self.boundary.root).argv
        self.assertEqual(argv[argv.index("--detail") + 1], "full")
