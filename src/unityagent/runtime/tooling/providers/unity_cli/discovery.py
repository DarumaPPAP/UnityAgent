"""Unity CLI の現在のcommand surfaceとProject/Pipeline bindingを動的観測する。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from unityagent.runtime.dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from unityagent.runtime.tooling.environment.project_identity import same_project_root
from unityagent.runtime.tooling.providers.unity_cli.command_builder import (
    build_commands_manifest_command,
    build_help_probe,
    build_pipeline_catalog_command,
    build_pipeline_command,
    build_project_info_command,
    build_status_command,
    build_version_command,
)
from unityagent.runtime.tooling.providers.unity_cli.result_mapper import (
    envelope_data,
    extract_command_catalog,
    extract_command_names,
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


def _structured_version(outcome: dict[str, Any]) -> str | None:
    try:
        envelope = terminal_envelope(parse_json_sequence(_stdout(outcome)))
    except ValueError:
        return None
    if envelope is None or envelope.get("success") is not True:
        return None
    data = envelope_data(envelope)
    if not isinstance(data, dict):
        return None
    value = data.get("version")
    return value.strip() if isinstance(value, str) and value.strip() else None


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

    supported: set[str] = set()
    structured_version_command = build_version_command(executable)
    version_outcome, dispatch_failure = _dispatch_safe(
        DispatchRequest(list(structured_version_command.argv), root, timeout_seconds),
        dispatch_fn=dispatch_fn,
    )
    version = _structured_version(version_outcome) if version_outcome is not None and _returncode(version_outcome) == 0 else None
    if version is not None:
        supported.add("version")
    else:
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
    if version is None:
        version_text = _stdout(version_outcome).strip()
        version = version_text.splitlines()[0].strip() if version_text else str(cli.get("version") or "") or None

    manifest_command = build_commands_manifest_command(executable)
    manifest_outcome, _ = _dispatch_safe(
        DispatchRequest(list(manifest_command.argv), root, timeout_seconds),
        dispatch_fn=dispatch_fn,
    )
    manifest_names = frozenset()
    if manifest_outcome is not None and _returncode(manifest_outcome) == 0:
        try:
            manifest_names = extract_command_names(_stdout(manifest_outcome))
        except ValueError:
            manifest_names = frozenset()
    if manifest_names:
        supported.update(manifest_names)
        supported.add("commands")
    else:
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

    pipeline = environment_snapshot.get("pipeline") or {}
    pipeline_reachable: bool | str = False if pipeline.get("installed") is False else "unknown"
    command_catalog: tuple[dict[str, Any], ...] = ()
    catalog_failure = None
    catalog_reason = None
    if pipeline.get("installed") is True and "command" in supported:
        # 全Editor列挙は無関係なProjectの応答待ちを含むため、対象ProjectのCatalogを直接観測する。
        command = build_pipeline_catalog_command(executable, root)
        outcome, dispatch_failure = _dispatch_safe(DispatchRequest(list(command.argv), root, timeout_seconds), dispatch_fn=dispatch_fn)
        pipeline_reachable = False
        if outcome is None:
            catalog_failure = dispatch_failure or "unavailable"
        elif outcome.get("failure_class") == "runtime_timeout":
            catalog_failure = "timeout"
        elif _returncode(outcome) != 0:
            catalog_failure = "unavailable"
        else:
            try:
                command_catalog = extract_command_catalog(_stdout(outcome))
            except ValueError:
                command_catalog = ()
            pipeline_reachable = bool(command_catalog)
            if not pipeline_reachable:
                catalog_failure = "not_observed"
        if catalog_failure:
            catalog_reason = "Target Project Pipeline Catalog was not observed: " + catalog_failure

    editor_status: Any | None = None
    if any(item["name"] == "editor_status" and item["runtime_only"] is False for item in command_catalog):
        # 固定Pipelineが公開する実名を使い、CLI status内部の互換probeを他Editorへ送らない。
        command = build_pipeline_command(executable, root, "editor_status")
        outcome, _ = _dispatch_safe(DispatchRequest(list(command.argv), root, timeout_seconds), dispatch_fn=dispatch_fn)
        if outcome is not None and _returncode(outcome) == 0:
            try:
                envelope = terminal_envelope(parse_json_sequence(_stdout(outcome), strict=True))
                data = envelope_data(envelope) if envelope and envelope.get("success") is True and envelope.get("errors") == [] and envelope.get("command") == "command editor_status" else None
                target = data.get("target") if isinstance(data, dict) else None
                result = data.get("result") if isinstance(data, dict) else None
                if isinstance(result, str):
                    values = parse_json_sequence(result, strict=True)
                    result = values[0] if len(values) == 1 else None
                bound = isinstance(target, dict) and isinstance(result, dict) and isinstance(target.get("projectPath"), str) and isinstance(result.get("projectPath"), str)
                if bound and same_project_root(target["projectPath"], str(root)) and same_project_root(result["projectPath"], str(root)) and isinstance(result.get("unityVersion"), str):
                    ready = result.get("status") == "ready" and result.get("compiling") is False and result.get("domainReloadInProgress") is False
                    editor_status = {"instances": [{"projectPath": result["projectPath"], "version": result["unityVersion"], "state": "ready" if ready else "busy"}]}
            except (ValueError, TypeError):
                editor_status = None
    elif "status" in supported:
        command = build_status_command(executable, root)
        outcome, _ = _dispatch_safe(DispatchRequest(list(command.argv), root, timeout_seconds), dispatch_fn=dispatch_fn)
        if outcome is not None:
            try:
                envelope = terminal_envelope(parse_json_sequence(_stdout(outcome)))
            except ValueError:
                envelope = None
            if envelope is not None:
                editor_status = envelope_data(envelope)

    return UnityCliSurfaceDiscovery(
        status="available",
        executable_path=str(executable),
        version=version,
        supported_commands=frozenset(supported),
        project_info=project_info,
        editor_status=editor_status,
        pipeline_reachable=pipeline_reachable,
        command_catalog=command_catalog,
        failure_class=catalog_failure,
        reason=catalog_reason,
    )
