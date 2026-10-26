from __future__ import annotations

import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unityagent.runtime.health.probes import probe_environment_snapshot
from unityagent.runtime.tooling.environment.discovery import (
    EnvironmentSnapshotCache,
    ProviderInstanceObservation,
    bind_provider_instances,
    discover_environment,
    probe_unity_cli,
)
from unityagent.runtime.tooling.environment.environment_snapshot import (
    UnityCliSnapshot,
    validate_environment_snapshot,
    validate_environment_snapshot_schema,
)
from unityagent.runtime.tooling.environment.native_editor_discovery import EditorCandidate, EditorProcessObservation, bind_editor_processes
from unityagent.runtime.tooling.environment.project_identity import canonicalize_project_root, same_project_root


class EnvironmentDiscoveryTests(unittest.TestCase):
    def make_project(self, root: Path, *, pipeline: bool = True, tests: bool = True) -> Path:
        project = root / "Project"
        (project / "Assets").mkdir(parents=True)
        (project / "Packages").mkdir()
        (project / "ProjectSettings").mkdir()
        (project / "ProjectSettings/ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.3.12f1\n", encoding="utf-8"
        )
        dependencies = []
        if pipeline:
            dependencies.append('"com.unity.pipeline": "1.0.0"')
        if tests:
            dependencies.append('"com.unity.test-framework": "1.4.5"')
        (project / "Packages/manifest.json").write_text(
            '{"dependencies": {' + ",".join(dependencies) + '}}', encoding="utf-8"
        )
        return project

    def editor(self, project: Path, *, pid: int = 10, safe_mode: bool = False) -> tuple[list[EditorCandidate], list[EditorProcessObservation]]:
        candidate = EditorCandidate("C:/Unity/6000.3.12f1/Editor/Unity.exe", "6000.3.12f1")
        process = EditorProcessObservation(
            pid=pid,
            executable_path=candidate.executable_path,
            command_line=f'Unity.exe -projectPath "{project}"' + (" -safeMode" if safe_mode else ""),
            project_root=str(project),
            safe_mode=safe_mode,
        )
        return [candidate], [process]

    def discover_fixture(self, project: Path, profile: str):
        candidates, processes = self.editor(project)
        cli_true = UnityCliSnapshot(True, "1.0.0", "/tools/unity", None)
        cli_false = UnityCliSnapshot(False, None, None, "unavailable")
        bound = [ProviderInstanceObservation("mcp-1", True, str(project))]
        empty: list[ProviderInstanceObservation] = []

        kwargs = dict(
            editor_candidates=candidates,
            editor_candidates_observed=True,
            editor_processes=processes,
            editor_processes_observed=True,
            which_fn=lambda name: "/usr/bin/git" if name == "git" else None,
        )
        if profile == "FULL":
            kwargs.update(unity_cli_observation=cli_true, provider_instances={"myunitymcp": bound, "coplay_mcp": empty})
        elif profile == "CLI_ONLY":
            kwargs.update(unity_cli_observation=cli_true, provider_instances={"myunitymcp": empty, "coplay_mcp": empty})
        elif profile == "MCP_ONLY":
            kwargs.update(unity_cli_observation=cli_false, provider_instances={"myunitymcp": bound, "coplay_mcp": empty})
        elif profile == "NATIVE_EDITOR":
            kwargs.update(unity_cli_observation=cli_false, provider_instances={"myunitymcp": empty, "coplay_mcp": empty})
        elif profile == "SAFE_MODE":
            candidates, processes = self.editor(project, safe_mode=True)
            kwargs.update(
                editor_candidates=candidates,
                editor_processes=processes,
                unity_cli_observation=cli_false,
                provider_instances={"myunitymcp": empty, "coplay_mcp": empty},
            )
        elif profile == "NO_EDITOR":
            kwargs.update(
                editor_candidates=[],
                editor_candidates_observed=True,
                editor_processes=[],
                unity_cli_observation=cli_false,
                provider_instances={"myunitymcp": empty, "coplay_mcp": empty},
            )
        elif profile == "FILES_ONLY":
            kwargs.update(
                editor_candidates=[],
                editor_candidates_observed=False,
                editor_processes=[],
                unity_cli_observation=cli_false,
                provider_instances={"myunitymcp": empty, "coplay_mcp": empty},
            )
        else:
            raise AssertionError(profile)
        return discover_environment(str(project), **kwargs)

    def test_required_environment_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            for profile in ("FULL", "CLI_ONLY", "MCP_ONLY", "NATIVE_EDITOR", "FILES_ONLY", "SAFE_MODE", "NO_EDITOR"):
                with self.subTest(profile=profile):
                    snapshot = self.discover_fixture(project, profile)
                    self.assertEqual(snapshot.profile_hint, profile)
                    snapshot.validate()

    def test_unknown_is_not_collapsed_to_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            snapshot = discover_environment(
                str(project),
                editor_candidates=[],
                editor_candidates_observed=False,
                editor_processes=[],
                editor_processes_observed=True,
                unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"),
                provider_instances=None,
                player_observation=None,
                which_fn=lambda _: None,
            )
            self.assertEqual(snapshot.myunitymcp.available, "unknown")
            self.assertEqual(snapshot.coplay_mcp.project_bound, "unknown")
            self.assertEqual(snapshot.player_runtime.reachable, "unknown")
            self.assertEqual(snapshot.build.requested_target_module_available, "unknown")

    def test_multiple_editor_instances_for_target_fail_closed(self):
        processes = [
            EditorProcessObservation(1, None, "Unity", "D:/Game", False),
            EditorProcessObservation(2, None, "Unity", "d:/game", False),
        ]
        result = bind_editor_processes("D:/GAME", processes, platform_name="Windows")
        self.assertTrue(result["running"])
        self.assertFalse(result["project_bound"])
        self.assertEqual(result["binding_status"], "ambiguous_binding")
        self.assertIsNone(result["bound_instance_id"])

    def test_wrong_project_mcp_is_unavailable_for_target(self):
        result = bind_provider_instances(
            "D:/GameA",
            [ProviderInstanceObservation("mcp-b", True, "D:/GameB")],
            platform_name="Windows",
        )
        self.assertTrue(result.reachable)
        self.assertFalse(result.available)
        self.assertFalse(result.project_bound)
        self.assertEqual(result.binding_status, "unbound")

    def test_ambiguous_mcp_binding_fails_closed(self):
        result = bind_provider_instances(
            "D:/Game",
            [
                ProviderInstanceObservation("mcp-1", True, "D:/Game"),
                ProviderInstanceObservation("mcp-2", True, "d:/game"),
            ],
            platform_name="Windows",
        )
        self.assertEqual(result.binding_status, "ambiguous_binding")
        self.assertFalse(result.available)
        self.assertFalse(result.project_bound)

    def test_windows_and_posix_path_normalization(self):
        left = canonicalize_project_root(r"C:\Work\Game\..\Game\Project", platform_name="Windows")
        right = canonicalize_project_root(r"c:/work/game/project", platform_name="Windows")
        self.assertEqual(left, right)
        self.assertTrue(same_project_root(left, right, platform_name="Windows"))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self.make_project(root)
            link = root / "ProjectLink"
            try:
                link.symlink_to(project, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are unavailable on this host")
            self.assertTrue(same_project_root(str(project), str(link), platform_name="Linux"))

    def test_cli_timeout_and_crash_are_bounded_and_not_available(self):
        seen = []

        def timeout_dispatch(request):
            seen.append(request.timeout_seconds)
            return {"status": "failed", "failure_class": "runtime_timeout"}

        timed_out = probe_unity_cli(
            cwd=Path.cwd(),
            which_fn=lambda name: "/tools/unity" if name == "unity" else None,
            dispatch_fn=timeout_dispatch,
            timeout_seconds=1.5,
        )
        self.assertFalse(timed_out.available)
        self.assertEqual(timed_out.failure_class, "timeout")
        self.assertEqual(seen, [1.5])

        crashed = probe_unity_cli(
            cwd=Path.cwd(),
            which_fn=lambda name: "/tools/unity" if name == "unity" else None,
            dispatch_fn=lambda request: {"status": "failed", "failure_class": "runtime_protocol_failure"},
        )
        self.assertFalse(crashed.available)
        self.assertEqual(crashed.failure_class, "unhealthy")

    def test_discovery_does_not_mutate_project_or_auto_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            before = sorted((path.relative_to(project).as_posix(), path.read_bytes()) for path in project.rglob("*") if path.is_file())
            calls = []

            def which(name):
                calls.append(name)
                return None

            discover_environment(
                str(project),
                mutation_allowed_paths=["Assets"],
                editor_candidates=[],
                editor_candidates_observed=True,
                editor_processes=[],
                editor_processes_observed=True,
                unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"),
                provider_instances={"myunitymcp": [], "coplay_mcp": []},
                which_fn=which,
            )
            after = sorted((path.relative_to(project).as_posix(), path.read_bytes()) for path in project.rglob("*") if path.is_file())
            self.assertEqual(before, after)
            self.assertEqual(calls, ["git"])

    def test_manifest_facts_and_mutation_scope_are_observations_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp), pipeline=True, tests=True)
            snapshot = discover_environment(
                str(project),
                mutation_allowed_paths=["Assets"],
                requested_build_target="StandaloneWindows64",
                requested_target_module_available=True,
                pipeline_reachable=True,
                editor_candidates=[],
                editor_candidates_observed=True,
                editor_processes=[],
                editor_processes_observed=True,
                unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"),
                provider_instances={"myunitymcp": [], "coplay_mcp": []},
                which_fn=lambda _: None,
            )
            self.assertTrue(snapshot.pipeline.installed)
            self.assertIs(snapshot.pipeline.reachable, True)
            self.assertTrue(snapshot.test_framework.available)
            self.assertTrue(snapshot.build.requested_target_module_available)
            self.assertTrue(snapshot.filesystem.writable_in_mutation_scope)

    def test_verified_artist_pipeline_observation_proves_project_pipeline_reachability(self):
        from unityagent.runtime.tooling.environment.environment_snapshot import ArtistSnapshot
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp), pipeline=True)
            artist = ArtistSnapshot(True, True, True, True, True, "6000.3.15f1", "builtin", "primary", "builtin_editor_api", "test", ["artist.inspect"], "bound", "fixture-project")
            snapshot = discover_environment(str(project), editor_candidates=[], editor_candidates_observed=True, editor_processes=[], editor_processes_observed=True, unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"), artist_observation=artist, which_fn=lambda _: None)
            self.assertIs(snapshot.pipeline.reachable, True)

    def test_bound_pipeline_version_identifies_custom_editor_without_guessing(self):
        from unityagent.runtime.tooling.environment.environment_snapshot import ArtistSnapshot
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            candidates, processes = self.editor(project)
            candidates = [EditorCandidate(candidates[0].executable_path, None)]
            artist = ArtistSnapshot(True, True, True, True, True, "6000.3.12f1", "builtin", "primary", "builtin_editor_api", "test", ["artist.inspect"], "bound", "fixture-project")
            snapshot = discover_environment(str(project), editor_candidates=candidates, editor_candidates_observed=True, editor_processes=processes, editor_processes_observed=True, unity_cli_observation=UnityCliSnapshot(True, "test", "/unity", None), artist_observation=artist, which_fn=lambda _: None)
            self.assertEqual(snapshot.unity_editor.version, "6000.3.12f1")
            self.assertIs(snapshot.unity_editor.project_version_match, True)

    def test_cache_invalidates_when_binding_fingerprint_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            first = self.discover_fixture(project, "FULL")
            candidates, processes = self.editor(project, pid=99)
            second = discover_environment(
                str(project),
                editor_candidates=candidates,
                editor_candidates_observed=True,
                editor_processes=processes,
                editor_processes_observed=True,
                unity_cli_observation=UnityCliSnapshot(True, "1.0", "/tools/unity", None),
                provider_instances={"myunitymcp": [ProviderInstanceObservation("mcp-2", True, str(project))], "coplay_mcp": []},
                which_fn=lambda name: "/usr/bin/git" if name == "git" else None,
            )
            self.assertNotEqual(first.binding_fingerprint, second.binding_fingerprint)
            cache = EnvironmentSnapshotCache()
            cache.put(first)
            self.assertIsNone(cache.get(str(project), binding_fingerprint=second.binding_fingerprint))

    def test_health_adapter_does_not_treat_optional_provider_absence_as_global_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            snapshot = self.discover_fixture(project, "NO_EDITOR").to_dict()
            health = probe_environment_snapshot(
                check_id="env",
                run_id="run",
                step_id="step",
                snapshot=snapshot,
                runtime_profile_revision="r1",
                tool_schema_revision="t1",
            )
            self.assertEqual(health["status"], "healthy")
            self.assertFalse(health["details"]["provider_availability"]["unity_cli"])

    def test_environment_snapshot_serializes_compatibility_tristate(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = self.discover_fixture(self.make_project(Path(tmp)), "NO_EDITOR").to_dict()
            self.assertIn("compatible", snapshot["artist"])
            self.assertNotIn("unity_artist_cli", snapshot)
            snapshot["artist"]["compatible"] = "unknown"
            validate_environment_snapshot(snapshot)

    def test_artist_pipeline_uses_unity_cli_catalog_and_observed_editor_support(self):
        from unityagent.runtime.tooling.environment.discovery import probe_artist_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            package = project / "ArtistPackage"
            package.mkdir()
            (package / "package.json").write_text(json.dumps({"name": "com.darumappap.artist-subagent", "version": "0.0.2-beta"}), encoding="utf-8")
            manifest = project / "Packages/manifest.json"
            manifest.write_text(json.dumps({"dependencies": {"com.unity.pipeline": "0.8.0-exp.1", "com.darumappap.artist-subagent": "file:" + package.as_posix()}}), encoding="utf-8")
            surface = SimpleNamespace(status="available", pipeline_reachable=True, command_catalog=({"name": "artist.inspect"}, {"name": "artist.capture"}))
            editor = {"schemaVersion": "2.0", "product": "UnityArtistCLI", "command": "artist.inspect", "status": "passed", "verified": True, "revision": "rev", "baseRevision": "rev", "approvalRequired": False, "savePerformed": False, "undoAvailable": True, "humanReview": False, "support": {"supported": True, "unityVersion": "6000.3.12f1", "renderPipeline": "builtin", "supportTier": "primary", "compatibilityBackend": "builtin_editor_api", "approvalProtocol": "control_plane_authority_v1", "contextProtocol": "artist_context_v1"}, "exactDiff": [], "targets": [], "errors": [], "evidence": ["visual_art_inspection", "pipeline_support_fact"]}
            calls = []
            def observe(value=editor, target=project):
                def dispatch_fixture(request):
                    calls.append(request.command)
                    return {"status": "passed", "payload": json.dumps({"success": True, "command": "command artist.inspect", "errors": [], "data": {"target": {"projectPath": str(target)}, "result": json.dumps(value)}})}
                return probe_artist_pipeline(project_root=str(project), cwd=project, unity_cli=UnityCliSnapshot(True, "1.0.0-beta.14", "/tools/unity", None), dispatch_fn=dispatch_fixture)
            with patch("unityagent.runtime.tooling.environment.discovery.discover_unity_cli_surface", return_value=surface):
                result = observe()
                self.assertIs(result.available, True)
                self.assertIs(result.compatible, True)
                self.assertEqual(result.package_version, "0.0.2-beta")
                self.assertEqual(result.capabilities, ["artist.capture", "artist.inspect"])
                self.assertIn("artist.inspect", calls[-1])
                self.assertIn(str(project), calls[-1])
                self.assertFalse(observe(target=project / "other").available)
                for key, bad in (("status", "unknown"), ("verified", False), ("schemaVersion", "future"), ("errors", [{"code": "FAILED"}])):
                    self.assertFalse(observe({**editor, key: bad}).available)
                for support in ({}, {**editor["support"], "supported": False}, {**editor["support"], "supportTier": "unknown"}, {**editor["support"], "unityVersion": "6000.7.0a2"}, {**editor["support"], "compatibilityBackend": "urp_native_api"}):
                    self.assertIsNot(observe({**editor, "support": support}).compatible, True)
            import io
            import tarfile
            tarball = project / "artist.tgz"
            metadata = json.dumps({"name": "com.darumappap.artist-subagent", "version": "0.0.2-beta"}).encode("utf-8")
            with tarfile.open(tarball, "w:gz") as archive:
                entry = tarfile.TarInfo("package/package.json")
                entry.size = len(metadata)
                archive.addfile(entry, io.BytesIO(metadata))
            manifest.write_text(json.dumps({"dependencies": {"com.unity.pipeline": "0.8.0-exp.1", "com.darumappap.artist-subagent": "file:" + tarball.as_posix()}}), encoding="utf-8")
            with patch("unityagent.runtime.tooling.environment.discovery.discover_unity_cli_surface", return_value=surface):
                self.assertTrue(observe().available)
                self.assertEqual(observe().package_version, "0.0.2-beta")
            tarball.write_bytes(b"invalid archive")
            calls.clear()
            self.assertFalse(observe().available)
            self.assertEqual(calls, [])
            manifest.write_text(json.dumps({"dependencies": {"com.unity.pipeline": "0.8.0-exp.1", "com.darumappap.artist-subagent": "file:" + package.as_posix()}}), encoding="utf-8")
            with patch("unityagent.runtime.tooling.environment.discovery.discover_unity_cli_surface", return_value=surface):
                for key in ("approvalProtocol", "contextProtocol"):
                    missing = {name: value for name, value in editor["support"].items() if name != key}
                    result = observe({**editor, "support": missing})
                    self.assertEqual(result.compatible, "unknown")
                    self.assertIs(result.available, False)
                    result = observe({**editor, "support": {**editor["support"], key: "legacy"}})
                    self.assertIs(result.compatible, False)
                    self.assertIs(result.available, False)
                self.assertTrue(all("artist.apply" not in argv for argv in calls))
            with patch("unityagent.runtime.tooling.environment.discovery.discover_unity_cli_surface", return_value=SimpleNamespace(status="available", pipeline_reachable=True, command_catalog=())):
                self.assertFalse(observe().available)

    def test_schema_is_valid(self):
        validate_environment_snapshot_schema()


    def test_retired_artist_host_snapshot_is_rejected(self):
        from jsonschema.exceptions import ValidationError
        with tempfile.TemporaryDirectory() as tmp:
            value = self.discover_fixture(self.make_project(Path(tmp)), "NO_EDITOR").to_dict()
            value["unity_artist_cli"] = {"available": False}
            with self.assertRaises(ValidationError):
                validate_environment_snapshot(value)

    def test_artist_absent_package_or_cli_never_dispatches(self):
        from unityagent.runtime.tooling.environment.discovery import probe_artist_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            def unexpected(_):
                raise AssertionError("Artist observation must not start subprocesses without prerequisites")
            result = probe_artist_pipeline(project_root=str(project), cwd=project, unity_cli=UnityCliSnapshot(True, "version", "/tools/unity", None), dispatch_fn=unexpected)
            self.assertFalse(result.available)
            self.assertFalse(result.package_installed)


if __name__ == "__main__":
    unittest.main()
