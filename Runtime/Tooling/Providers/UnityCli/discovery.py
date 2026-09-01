"""Unity CLI の現在のcommand surfaceとProject/Pipeline bindingを動的観測する。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.Providers.UnityCli.command_builder import (
    build_help_probe,
    build_pipeline_catalog_command,
    build_pipeline_list_command,
    build_project_info_command,
    build_status_command,
)
from Runtime.Tooling.Providers.UnityCli.result_mapper import (
    envelope_data,
    extract_command_catalog,
    normalize_project_info,
    parse_json_sequence,
    terminal_envelope,
)

DISCOVERY_COMMANDS = (
    "projects",
    "run",
    "test",
    "build",
    "status",
    "pipeline",
    "command",
    "shell",
)
DISCOVERY_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class UnityCliSurfaceDiscovery:
    status: str
    executable_path: str | None
    version: str | None
    supported_commands: frozenset[str]
    project_info: dict[str, Any] | None
    editor_status: Any | None
    pipeline_reachable: bool | str
    command_catalog: tuple[dict[str, Any], ...]
    failure_class: str | None = None
    reason: str | None = None


def _returncode(outcome: dict[str, Any]) -> int | None:
    result = outcome.get("result")
    value = getattr(result, "returncode", None) if result is not None else None
    return int(value) if isinstance(value, int) else None


def _stdout(outcome: dict[str, Any]) -> str:
    result = outcome.get("result")
    if result is not None:
        return str(getattr(result, "stdout", "") or "")
    return str(outcome.get("payload") or "")


def _dispatch_safe(
    request: DispatchRequest,
    *,
    dispatch_fn: Callable[..., dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return dispatch_fn(request), None
    except PermissionError:
        return None, "permission_denied"
    except OSError:
        return None, "unhealthy"


def _structured_success(outcome: dict[str, Any]) -> bool:
    try:
        envelope = terminal_envelope(parse_json_sequence(_stdout(outcome)))
    except ValueError:
        return False
    return envelope is not None and envelope.get("success") is True


def _project_info_root(project_info: dict[str, Any]) -> str | None:
    for key in ("path", "projectPath", "project_path", "root"):
        value = project_info.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def discover_unity_cli_surface(
    project_root: str | Path,
    environment_snapshot: dict[str, Any],
    *,
    dispatch_fn: Callable[..., dict[str, Any]] = dispatch,
    timeout_seconds: float = DISCOVERY_TIMEOUT_SECONDS,
) -> UnityCliSurfaceDiscovery:
    root = Path(project_root).expanduser().resolve()
    cli = environment_snapshot.get("unity_cli") or {}
    if cli.get("available") is not True:
        return UnityCliSurfaceDiscovery(
            status="unavailable",
            executable_path=None,
            version=None,
            supported_commands=frozenset(),
            project_info=None,
            editor_status=None,
            pipeline_reachable=False,
            command_catalog=(),
            failure_class="unavailable",
            reason="Unity CLI is not observed available",
        )
    executable_raw = cli.get("executable_path")
    if not isinstance(executable_raw, str) or not executable_raw.strip():
        return UnityCliSurfaceDiscovery(
            status="unavailable",
            executable_path=None,
            version=None,
            supported_commands=frozenset(),
            project_info=None,
            editor_status=None,
            pipeline_reachable=False,
            command_catalog=(),
            failure_class="unavailable",
            reason="Unity CLI executable path is not observed",
        )
    executable = Path(executable_raw).expanduser().resolve(strict=False)
    if not executable.is_file():
        return UnityCliSurfaceDiscovery(
            status="unavailable",
            executable_path=str(executable),
            version=None,
            supported_commands=frozenset(),
            project_info=None,
            editor_status=None,
            pipeline_reachable=False,
            command_catalog=(),
            failure_class="unavailable",
            reason="Unity CLI executable no longer exists",
        )

    version_outcome, dispatch_failure = _dispatch_safe(
        DispatchRequest([str(executable), "--version"], root, timeout_seconds),
        dispatch_fn=dispatch_fn,
    )
    if version_outcome is None:
        return UnityCliSurfaceDiscovery(
            status="unhealthy",
            executable_path=str(executable),
            version=None,
            supported_commands=frozenset(),
            project_info=None,
            editor_status=None,
            pipeline_reachable=False,
            command_catalog=(),
            failure_class=dispatch_failure,
            reason="Unity CLI health probe could not start",
        )
    version_code = _returncode(version_outcome)
    if version_code != 0:
        failure_class = "timeout" if version_outcome.get("failure_class") == "runtime_timeout" else "unhealthy"
        return UnityCliSurfaceDiscovery(
            status="unhealthy",
            executable_path=str(executable),
            version=None,
            supported_commands=frozenset(),
            project_info=None,
            editor_status=None,
            pipeline_reachable=False,
            command_catalog=(),
            failure_class=failure_class,
            reason="Unity CLI --version failed",
        )
    version_text = _stdout(version_outcome).strip()
    version = version_text.splitlines()[0].strip() if version_text else str(cli.get("version") or "") or None

    supported: set[str] = set()
    for command_name in DISCOVERY_COMMANDS:
        command = build_help_probe(executable, command_name)
        outcome, _ = _dispatch_safe(
            DispatchRequest(list(command.argv), root, timeout_seconds),
            dispatch_fn=dispatch_fn,
        )
        if outcome is not None and _returncode(outcome) == 0:
            supported.add(command_name)

    project_info: dict[str, Any] | None = None
    if "projects" in supported:
        command = build_project_info_command(executable, root)
        outcome, _ = _dispatch_safe(
            DispatchRequest(list(command.argv), root, timeout_seconds),
            dispatch_fn=dispatch_fn,
        )
        if outcome is not None:
            result = normalize_project_info(exit_code=_returncode(outcome) or 0, stdout=_stdout(outcome))
            if result.get("status") == "passed" and isinstance(result.get("project"), dict):
                candidate = dict(result["project"])
                observed_root = _project_info_root(candidate)
                if observed_root is None or same_project_root(observed_root, str(root)):
                    project_info = candidate

    editor_status: Any | None = None
    if "status" in supported:
        command = build_status_command(executable)
        outcome, _ = _dispatch_safe(
            DispatchRequest(list(command.argv), root, timeout_seconds),
            dispatch_fn=dispatch_fn,
        )
        if outcome is not None:
            try:
                envelope = terminal_envelope(parse_json_sequence(_stdout(outcome)))
            except ValueError:
                envelope = None
            if envelope is not None:
                editor_status = envelope_data(envelope)

    pipeline = environment_snapshot.get("pipeline") or {}
    pipeline_reachable: bool | str = False if pipeline.get("installed") is False else "unknown"
    command_catalog: tuple[dict[str, Any], ...] = ()
    if pipeline.get("installed") is True and "pipeline" in supported:
        command = build_pipeline_list_command(executable)
        outcome, _ = _dispatch_safe(
            DispatchRequest(list(command.argv), root, timeout_seconds),
            dispatch_fn=dispatch_fn,
        )
        pipeline_reachable = bool(outcome is not None and _returncode(outcome) == 0 and _structured_success(outcome))

    if pipeline_reachable is True and "command" in supported:
        command = build_pipeline_catalog_command(executable, root)
        outcome, _ = _dispatch_safe(
            DispatchRequest(list(command.argv), root, timeout_seconds),
            dispatch_fn=dispatch_fn,
        )
        if outcome is not None and _returncode(outcome) == 0:
            try:
                command_catalog = extract_command_catalog(_stdout(outcome))
            except ValueError:
                command_catalog = ()

    return UnityCliSurfaceDiscovery(
        status="available",
        executable_path=str(executable),
        version=version,
        supported_commands=frozenset(supported),
        project_info=project_info,
        editor_status=editor_status,
        pipeline_reachable=pipeline_reachable,
        command_catalog=command_catalog,
    )
