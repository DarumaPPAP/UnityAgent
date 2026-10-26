"""Read-only, environment-adaptive Unity Runtime discovery.

This module observes environment facts only. It does not select providers, install
missing tools, expand Mutation Scope, or perform semantic replanning.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from unityagent.runtime.dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from unityagent.runtime.tooling.environment.environment_snapshot import (
    ArtistSnapshot,
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
from unityagent.runtime.tooling.providers.unity_cli.discovery import discover_unity_cli_surface
from unityagent.runtime.tooling.providers.unity_cli.command_builder import build_pipeline_command
from unityagent.runtime.tooling.providers.unity_cli.result_mapper import parse_json_sequence, terminal_envelope
from unityagent.runtime.tooling.environment.native_editor_discovery import (
    EditorCandidate,
    EditorProcessObservation,
    bind_editor_processes,
    discover_editor_processes,
    enumerate_native_editor_candidates,
)
from unityagent.runtime.tooling.environment.project_identity import (
    canonicalize_project_root,
    observe_project_identity,
    same_project_root,
)

CLI_TIMEOUT_SECONDS = 5.0
ARTIST_CLI_TIMEOUT_SECONDS = 8.0
_ARTIST_COMPATIBILITY_BACKENDS = {
    "builtin_editor_api": "builtin",
    "urp_native_api": "urp",
    "hdrp_native_api": "hdrp",
}
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


def _manifest_package_version(project_root: str, package_name: str) -> str | None:
    manifest = Path(project_root).expanduser() / "Packages/manifest.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    dependencies = value.get("dependencies") if isinstance(value, dict) else None
    version = dependencies.get(package_name) if isinstance(dependencies, dict) else None
    return str(version) if isinstance(version, str) else None


def _support_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _artist_compatibility(
    *,
    unity_version: str | None,
    render_pipeline: str | None,
    support_tier: str | None,
    compatibility_backend: str | None,
) -> TriState:
    observed = (unity_version, render_pipeline, support_tier, compatibility_backend)
    if any(
        not isinstance(value, str)
        or not value.strip()
        or value.strip().casefold() in {"unknown", "not_observed", "unobserved"}
        for value in observed
    ):
        return "unknown"
    return (
        (unity_version.startswith("6000.") or unity_version.startswith("Unity 6"))
        and
        support_tier.casefold() == "primary"
        and _ARTIST_COMPATIBILITY_BACKENDS.get(compatibility_backend.casefold())
        == render_pipeline.casefold()
    )


def probe_artist_pipeline(*, project_root: str, cwd: Path, unity_cli: UnityCliSnapshot, dispatch_fn: Callable[..., dict] = dispatch, timeout_seconds: float = ARTIST_CLI_TIMEOUT_SECONDS) -> ArtistSnapshot:
    """公式Unity CLIのCatalogと対象ProjectのEditor応答だけでArtistを観測する。"""
    package_name = "com.darumappap.artist-subagent"
    package_installed = _package_fact(project_root, package_name)
    package_version = _manifest_package_version(project_root, package_name)
    if package_version and package_version.startswith("file:"):
        location = Path(package_version[5:])
        location = location if location.is_absolute() else Path(project_root) / "Packages" / location
        try:
            if location.is_file():
                # Unityのlocal-tarballは展開・実行せず、正規Package metadataだけを観測する。
                with tarfile.open(location, "r:*") as archive:
                    entry = archive.getmember("package/package.json")
                    if not entry.isfile() or entry.size > 65536:
                        raise ValueError("Artist Package metadata must be a bounded regular file")
                    with archive.extractfile(entry) as stream:
                        package = json.loads(stream.read().decode("utf-8-sig"))
            else:
                package = json.loads((location / "package.json").read_text(encoding="utf-8-sig"))
            package_version = _support_text(package.get("version")) if isinstance(package, dict) and package.get("name") == package_name else None
            package_installed = package_version is not None
        except (OSError, UnicodeError, ValueError, KeyError, tarfile.TarError):
            package_installed, package_version = False, None
    empty = ArtistSnapshot(False, "unknown", "unknown", package_installed, "unknown", None, None, None, None, package_version, [], "unknown", None)
    # Packageも公式CLIも未観測なら、無関係なHost探索やEditor操作を始める根拠がない。
    if package_installed is not True or unity_cli.available is not True or not unity_cli.executable_path:
        return empty
    surface = discover_unity_cli_surface(project_root, {"unity_cli": {"available": unity_cli.available, "executable_path": unity_cli.executable_path}, "pipeline": {"installed": _package_fact(project_root, PIPELINE_PACKAGE)}}, dispatch_fn=dispatch_fn, timeout_seconds=timeout_seconds)
    names = sorted({item["name"] for item in surface.command_catalog if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].startswith("artist.")})
    empty = ArtistSnapshot(**{**empty.__dict__, "pipeline_reachable": surface.pipeline_reachable, "capabilities": names})
    # CatalogにないCommandを能力として推測して実行しない。
    if surface.status != "available" or surface.pipeline_reachable is not True or "artist.inspect" not in names:
        return empty
    command = build_pipeline_command(unity_cli.executable_path, project_root, "artist.inspect", [])
    try:
        outcome = dispatch_fn(DispatchRequest(list(command.argv), cwd, timeout_seconds))
        raw = outcome.get("payload")
        if raw is None:
            raw = getattr(outcome.get("result"), "stdout", "")
        envelope = terminal_envelope(parse_json_sequence(raw, strict=True))
        if outcome.get("status") != "passed" or envelope is None or envelope.get("success") is not True or envelope.get("errors") != [] or envelope.get("command") not in {"command", "command artist.inspect"}:
            return empty
        data = envelope.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("target"), dict) or not isinstance(data["target"].get("projectPath"), str) or not same_project_root(data["target"]["projectPath"], project_root):
            return ArtistSnapshot(**{**empty.__dict__, "project_bound": False, "binding_status": "unbound"})
        raw_editor = data.get("result")
        values = parse_json_sequence(raw_editor, strict=True) if isinstance(raw_editor, str) else [raw_editor]
        editor = values[0] if len(values) == 1 else None
        if not isinstance(editor, dict):
            return empty
        support = editor.get("support")
        if not isinstance(support, dict):
            return empty
        unity_version = _support_text(support.get("unityVersion"))
        render_pipeline = _support_text(support.get("renderPipeline"))
        support_tier = _support_text(support.get("supportTier"))
        backend = _support_text(support.get("compatibilityBackend"))
        compatible = _artist_compatibility(unity_version=unity_version, render_pipeline=render_pipeline, support_tier=support_tier, compatibility_backend=backend)
        expected_version = observe_project_identity(project_root)["unity_version"]
        if support.get("supported") is not True or not expected_version or expected_version != unity_version:
            compatible = False
        # 同versionの旧Assemblyが応答しても、実Mutation前の認証・Context契約を推測で有効化しない。
        protocols = {"approvalProtocol": "control_plane_authority_v1", "contextProtocol": "artist_context_v1"}
        for name, expected in protocols.items():
            observed = support.get(name)
            if observed is None or observed == "" or observed == "unknown":
                if compatible is not False:
                    compatible = "unknown"
            elif observed != expected:
                compatible = False
        # 正規化器と同じ構造・Revision・Evidence契約を満たした観測だけを利用可能とする。
        from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand
        from unityagent.runtime.tooling.providers.unity_cli.artist_result_mapper import normalize_artist_pipeline_result
        normalized = normalize_artist_pipeline_result(exit_code=0, stdout=raw, command=ArtistCommand("inspect"), project_root=project_root, unity_version=expected_version or "", render_pipeline=render_pipeline or "")
        available = compatible is True and normalized.get("status") == "passed"
        return ArtistSnapshot(available, compatible if normalized.get("status") == "passed" else False, True, package_installed, True, unity_version, render_pipeline, support_tier, backend, package_version, names, "bound", "unity-cli:" + canonicalize_project_root(project_root))
    except (OSError, ValueError, TypeError, RuntimeError):
        return empty


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
        "artist": None if snapshot.artist is None else {
            "status": snapshot.artist.binding_status,
            "instance": snapshot.artist.bound_instance_id,
            "package_version": snapshot.artist.package_version,
        },
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
    artist_observation: ArtistSnapshot | None = None,
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
    artist = artist_observation or probe_artist_pipeline(project_root=canonical_root, cwd=cwd, unity_cli=unity_cli, dispatch_fn=dispatch_fn)
    if unity_editor.installed is True and unity_editor.version is None and unity_editor.binding_status == "bound" and unity_editor.project_bound is True and artist.project_bound is True and artist.pipeline_reachable is True and artist.unity_version and artist.unity_version == project["unity_version"]:
        unity_editor = replace(unity_editor, version=artist.unity_version, project_version_match=True)

    pipeline_installed = _package_fact(project_root, PIPELINE_PACKAGE)
    if pipeline_installed is False:
        pipeline_reachable = False
    elif pipeline_installed is True and pipeline_reachable == "unknown" and artist.project_bound is True and artist.pipeline_reachable is True:
        pipeline_reachable = True
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
        artist=artist,
    )
    profile = _derive_profile(base)
    fingerprint = _binding_fingerprint(base)
    snapshot = EnvironmentSnapshot(**{**base.__dict__, "profile_hint": profile, "binding_fingerprint": fingerprint})
    snapshot.validate()
    return snapshot
