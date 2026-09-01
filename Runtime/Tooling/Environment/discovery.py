"""Read-only, environment-adaptive Unity Runtime discovery.

This module observes environment facts only. It does not select providers, install
missing tools, expand Mutation Scope, or perform semantic replanning.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from Runtime.Tooling.Environment.environment_snapshot import (
    AvailabilitySnapshot,
    BuildSnapshot,
    EnvironmentSnapshot,
    FilesystemSnapshot,
    GitSnapshot,
    PipelineSnapshot,
    PlayerRuntimeSnapshot,
    ProjectSnapshot,
    ProviderBindingSnapshot,
    TriState,
    UnityCliSnapshot,
    UnityEditorSnapshot,
)
from Runtime.Tooling.Environment.native_editor_discovery import (
    EditorCandidate,
    EditorProcessObservation,
    bind_editor_processes,
    discover_editor_processes,
    enumerate_native_editor_candidates,
)
from Runtime.Tooling.Environment.project_identity import (
    canonicalize_project_root,
    observe_project_identity,
    same_project_root,
)

CLI_TIMEOUT_SECONDS = 5.0
PIPELINE_PACKAGE = "com.unity.pipeline"
TEST_FRAMEWORK_PACKAGE = "com.unity.test-framework"


@dataclass(frozen=True)
class ProviderInstanceObservation:
    instance_id: str
    reachable: TriState
    project_root: str | None


@dataclass(frozen=True)
class PlayerObservation:
    reachable: TriState
    instance_id: str | None = None


class EnvironmentSnapshotCache:
    """Optional in-memory cache that fails closed when editor/provider identity changes."""

    def __init__(self) -> None:
        self._items: dict[str, EnvironmentSnapshot] = {}

    def put(self, snapshot: EnvironmentSnapshot) -> None:
        self._items[snapshot.project.root] = snapshot

    def get(self, project_root: str, *, binding_fingerprint: str) -> EnvironmentSnapshot | None:
        key = canonicalize_project_root(project_root)
        current = self._items.get(key)
        if current is None:
            return None
        if current.binding_fingerprint != binding_fingerprint:
            self._items.pop(key, None)
            return None
        return current

    def invalidate(self, project_root: str) -> None:
        self._items.pop(canonicalize_project_root(project_root), None)


def _nearest_existing(path: Path) -> Path | None:
    current = path
    while True:
        if current.exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _observe_scope_writable(project_root: Path, allowed_paths: Sequence[str] | None) -> TriState:
    if allowed_paths is None:
        return "unknown"
    if not allowed_paths:
        return False
    root = project_root.resolve(strict=False)
    observed: list[bool] = []
    for value in allowed_paths:
        if not isinstance(value, str) or not value.strip():
            return False
        candidate = Path(value)
        if candidate.is_absolute():
            target = candidate.resolve(strict=False)
        else:
            target = (root / candidate).resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError:
            return False
        existing = _nearest_existing(target)
        if existing is None:
            return "unknown"
        observed.append(os.access(existing, os.W_OK))
    return all(observed)


def observe_filesystem(project_root: str, *, mutation_allowed_paths: Sequence[str] | None = None) -> FilesystemSnapshot:
    root = Path(project_root).expanduser().resolve(strict=False)
    if not root.is_dir():
        return FilesystemSnapshot(False, False, "unknown" if mutation_allowed_paths is None else False)
    return FilesystemSnapshot(
        readable=os.access(root, os.R_OK),
        writable=os.access(root, os.W_OK),
        writable_in_mutation_scope=_observe_scope_writable(root, mutation_allowed_paths),
    )


def observe_git(project_root: str, *, which_fn: Callable[[str], str | None] = shutil.which) -> GitSnapshot:
    root = Path(project_root).expanduser().resolve(strict=False)
    repository_bound = False
    if root.exists():
        for candidate in (root, *root.parents):
            marker = candidate / ".git"
            if marker.exists():
                repository_bound = True
                break
    return GitSnapshot(available=which_fn("git") is not None, repository_bound=repository_bound)


def _package_fact(project_root: str, package_name: str) -> TriState:
    manifest = Path(project_root).expanduser() / "Packages/manifest.json"
    if not manifest.is_file():
        return "unknown"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "unknown"
    dependencies = value.get("dependencies") if isinstance(value, dict) else None
    if not isinstance(dependencies, dict):
        return "unknown"
    return package_name in dependencies


def probe_unity_cli(
    *,
    cwd: Path,
    explicit_executable: str | None = None,
    which_fn: Callable[[str], str | None] = shutil.which,
    dispatch_fn: Callable[..., dict] = dispatch,
    timeout_seconds: float = CLI_TIMEOUT_SECONDS,
) -> UnityCliSnapshot:
    executable = explicit_executable
    if executable is not None:
        executable_path = Path(executable).expanduser()
        executable = str(executable_path.resolve(strict=False)) if executable_path.is_file() else None
    if executable is None:
        executable = which_fn("unity") or which_fn("unity-cli")
    if executable is None:
        return UnityCliSnapshot(False, None, None, "unavailable")

    outcome = dispatch_fn(DispatchRequest([executable, "--version"], cwd, timeout_seconds))
    if outcome.get("status") != "passed":
        failure = "timeout" if outcome.get("failure_class") == "runtime_timeout" else "unhealthy"
        return UnityCliSnapshot(False, None, executable, failure)
    version_text = str(outcome.get("payload") or "").strip()
    version = version_text.splitlines()[0].strip() if version_text else None
    return UnityCliSnapshot(True, version, executable, None)


def bind_provider_instances(
    target_project_root: str,
    instances: Sequence[ProviderInstanceObservation] | None,
    *,
    platform_name: str | None = None,
) -> ProviderBindingSnapshot:
    """Bind structured MCP/provider observations to exactly one target project instance."""
    if instances is None:
        return ProviderBindingSnapshot("unknown", "unknown", "unknown", "unknown", None)
    if not instances:
        return ProviderBindingSnapshot(False, False, False, "unbound", None)

    reachable = [item for item in instances if item.reachable is True]
    unknown_reachability = any(item.reachable == "unknown" for item in instances)
    if not reachable:
        if unknown_reachability:
            return ProviderBindingSnapshot("unknown", "unknown", "unknown", "unknown", None)
        return ProviderBindingSnapshot(False, False, False, "unbound", None)

    matching = [
        item
        for item in reachable
        if item.project_root is not None
        and same_project_root(item.project_root, target_project_root, platform_name=platform_name)
    ]
    if len(matching) == 1:
        return ProviderBindingSnapshot(True, True, True, "bound", matching[0].instance_id)
    if len(matching) > 1:
        return ProviderBindingSnapshot(True, False, False, "ambiguous_binding", None)
    return ProviderBindingSnapshot(True, False, False, "unbound", None)


def _select_editor_candidate(
    candidates: Sequence[EditorCandidate], project_version: str | None
) -> EditorCandidate | None:
    if not candidates:
        return None
    if project_version:
        exact = [candidate for candidate in candidates if candidate.version == project_version]
        if exact:
            return exact[0]
    return candidates[0]


def _derive_profile(snapshot: EnvironmentSnapshot) -> str | None:
    if snapshot.unity_editor.safe_mode is True:
        return "SAFE_MODE"

    cli = snapshot.unity_cli.available
    mcp_values = (snapshot.myunitymcp.available, snapshot.coplay_mcp.available)
    mcp_true = any(value is True for value in mcp_values)
    mcp_false = all(value is False for value in mcp_values)

    if cli is True and mcp_true:
        return "FULL"
    if cli is True and mcp_false:
        return "CLI_ONLY"
    if cli is False and mcp_true:
        return "MCP_ONLY"
    if cli is False and mcp_false and snapshot.unity_editor.installed is True:
        return "NATIVE_EDITOR"
    if snapshot.unity_editor.installed is False:
        return "NO_EDITOR"
    if cli is False and mcp_false and snapshot.filesystem.readable is True:
        return "FILES_ONLY"
    if snapshot.player_runtime.reachable is False:
        return "PLAYER_UNAVAILABLE"
    return None


def _binding_fingerprint(snapshot: EnvironmentSnapshot) -> str:
    material = {
        "project_root": snapshot.project.root,
        "unity_editor": {
            "status": snapshot.unity_editor.binding_status,
            "instance": snapshot.unity_editor.bound_instance_id,
        },
        "myunitymcp": {
            "status": snapshot.myunitymcp.binding_status,
            "instance": snapshot.myunitymcp.bound_instance_id,
        },
        "coplay_mcp": {
            "status": snapshot.coplay_mcp.binding_status,
            "instance": snapshot.coplay_mcp.bound_instance_id,
        },
        "player_runtime": snapshot.player_runtime.instance_id,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def discover_environment(
    project_root: str,
    *,
    mutation_allowed_paths: Sequence[str] | None = None,
    requested_build_target: str | None = None,
    requested_target_module_available: TriState = "unknown",
    pipeline_reachable: TriState = "unknown",
    provider_instances: Mapping[str, Sequence[ProviderInstanceObservation] | None] | None = None,
    player_observation: PlayerObservation | None = None,
    editor_candidates: Sequence[EditorCandidate] | None = None,
    editor_candidates_observed: bool = False,
    editor_processes: Sequence[EditorProcessObservation] | None = None,
    editor_processes_observed: bool = False,
    unity_cli_observation: UnityCliSnapshot | None = None,
    explicit_unity_cli: str | None = None,
    platform_name: str | None = None,
    which_fn: Callable[[str], str | None] = shutil.which,
    dispatch_fn: Callable[..., dict] = dispatch,
) -> EnvironmentSnapshot:
    """Create a deterministic snapshot from observed facts without mutating the project."""
    project = observe_project_identity(project_root)
    canonical_root = project["root"]
    root_path = Path(project_root).expanduser().resolve(strict=False)
    cwd = root_path if root_path.is_dir() else Path.cwd()

    filesystem = observe_filesystem(project_root, mutation_allowed_paths=mutation_allowed_paths)
    git = observe_git(project_root, which_fn=which_fn)

    candidates = list(editor_candidates) if editor_candidates is not None else enumerate_native_editor_candidates(
        project_version=project["unity_version"], platform_name=platform_name
    )

    processes: Sequence[EditorProcessObservation] | None
    if editor_processes_observed:
        processes = list(editor_processes or [])
    elif editor_processes is not None:
        processes = list(editor_processes)
    else:
        processes = discover_editor_processes(cwd=cwd, platform_name=platform_name, dispatch_fn=dispatch_fn)

    # A running process with a concrete executable is also an installation fact.
    if not candidates and processes:
        process_paths = [item.executable_path for item in processes if item.executable_path]
        if process_paths:
            candidates = [EditorCandidate(process_paths[0], None)]

    selected_editor = _select_editor_candidate(candidates, project["unity_version"])
    editor_binding = bind_editor_processes(canonical_root, processes, platform_name=platform_name)
    if selected_editor is None:
        installed: TriState = False if editor_candidates_observed else "unknown"
        editor_version = None
        editor_path = None
        project_version_match: TriState = "unknown"
    else:
        installed = True
        editor_version = selected_editor.version
        editor_path = selected_editor.executable_path
        if project["unity_version"] is None or selected_editor.version is None:
            project_version_match = "unknown"
        else:
            project_version_match = selected_editor.version == project["unity_version"]

    unity_editor = UnityEditorSnapshot(
        installed=installed,
        version=editor_version,
        executable_path=editor_path,
        project_version_match=project_version_match,
        running=editor_binding["running"],
        safe_mode=editor_binding["safe_mode"],
        project_bound=editor_binding["project_bound"],
        binding_status=editor_binding["binding_status"],
        bound_instance_id=editor_binding["bound_instance_id"],
    )

    unity_cli = unity_cli_observation or probe_unity_cli(
        cwd=cwd,
        explicit_executable=explicit_unity_cli,
        which_fn=which_fn,
        dispatch_fn=dispatch_fn,
    )

    pipeline_installed = _package_fact(project_root, PIPELINE_PACKAGE)
    if pipeline_installed is False:
        pipeline_reachable = False
    pipeline = PipelineSnapshot(pipeline_installed, pipeline_reachable)

    instances = provider_instances or {}
    myunitymcp = bind_provider_instances(canonical_root, instances.get("myunitymcp"), platform_name=platform_name)
    coplay_mcp = bind_provider_instances(canonical_root, instances.get("coplay_mcp"), platform_name=platform_name)

    test_framework = AvailabilitySnapshot(_package_fact(project_root, TEST_FRAMEWORK_PACKAGE))
    build = BuildSnapshot(requested_build_target, requested_target_module_available)
    player_runtime = PlayerRuntimeSnapshot(
        "unknown" if player_observation is None else player_observation.reachable,
        None if player_observation is None else player_observation.instance_id,
    )

    base = EnvironmentSnapshot(
        schema_version="1.0",
        project=ProjectSnapshot(**project),
        filesystem=filesystem,
        git=git,
        unity_editor=unity_editor,
        unity_cli=unity_cli,
        pipeline=pipeline,
        myunitymcp=myunitymcp,
        coplay_mcp=coplay_mcp,
        test_framework=test_framework,
        build=build,
        player_runtime=player_runtime,
        profile_hint=None,
        binding_fingerprint="0" * 64,
    )
    profile = _derive_profile(base)
    fingerprint = _binding_fingerprint(base)
    snapshot = EnvironmentSnapshot(**{**base.__dict__, "profile_hint": profile, "binding_fingerprint": fingerprint})
    snapshot.validate()
    return snapshot
