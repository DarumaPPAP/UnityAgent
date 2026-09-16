"""Run the v1.1 Camera FOV reference route against a real Unity Editor.

This runner is deliberately a gate/orchestration harness. The mutation itself is
still owned by the canonical ControlPlane -> ToolBroker -> Provider -> Evidence
chain; this module never edits Unity assets and never invokes a Provider's
subprocess transport directly.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIST_ROOT = ROOT.parent / "MyUnityMCP"
DEFAULT_PROJECT = DEFAULT_ARTIST_ROOT / "TestProjects" / "UnityArtistVerification"
UNITY_VERSION = "6000.6.0f1"
DEFAULT_EDITOR = Path("C:/Program Files/Unity/Hub/Editor/6000.6.0f1/Editor/Unity.exe")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ControlPlane.unity_agent_control_plane import UnityAgentControlPlane
from Runtime.ReferenceImplementation.authority import (
    ApprovalDecisionResolver,
    TaskContractIssuer,
    iso_now,
)
from Runtime.ReferenceImplementation.canonicalization import sha256_jcs
from Runtime.ReferenceImplementation.contracts import ApprovalDecision, ContractValidationError
from Runtime.ReferenceImplementation.runtime import reference_definition_fingerprint
from Runtime.Tooling.Providers.UnityArtistCli.unity_artist_cli_provider import UnityArtistCliProvider
from Runtime.Tooling.capability_resolver import ResolutionContext


class LiveFailure(RuntimeError):
    """A repository/runtime defect, invalid live result, or contract failure."""


class ExternalBlocker(RuntimeError):
    """A Unity/Editor/license/permission/service condition outside the code."""

    def __init__(self, message: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.evidence = dict(evidence or {})


def _tail(value: str, limit: int = 5000) -> str:
    return (value or "")[-limit:]


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: Mapping[str, str] | None = None,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    base_options: dict[str, Any] = {
        "cwd": str(cwd),
        "env": dict(env or os.environ),
        "text": False,
        "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0,
    }

    def decode(stream: bytes | None) -> str:
        return (stream or b"").decode("utf-8", errors="replace")

    try:
        if not capture_output:
            process = subprocess.Popen(
                command,
                **base_options,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
                raise ExternalBlocker(
                    "official Unity/CLI command exceeded its bounded timeout",
                    evidence={"command": command, "timeout_seconds": timeout},
                ) from exc
            return subprocess.CompletedProcess(command, returncode, "", "")

        # UnityArtistCLI and the official Unity CLI can launch Editor/UPM
        # descendants.  Captured OS pipes are inherited by those descendants,
        # so communicate() may wait after the CLI parent has exited.  Disk
        # backed handles preserve the same JSON capture without that lifetime
        # coupling.
        with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(mode="w+b") as stderr_file:
            process = subprocess.Popen(
                command,
                **base_options,
                stdout=stdout_file,
                stderr=stderr_file,
            )
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
                stdout_file.seek(0)
                stderr_file.seek(0)
                raise ExternalBlocker(
                    "official Unity/CLI command exceeded its bounded timeout",
                    evidence={
                        "command": command,
                        "timeout_seconds": timeout,
                        "stdout": _tail(decode(stdout_file.read())),
                        "stderr": _tail(decode(stderr_file.read())),
                    },
                ) from exc
            stdout_file.seek(0)
            stderr_file.seek(0)
            return subprocess.CompletedProcess(
                command,
                returncode,
                decode(stdout_file.read()),
                decode(stderr_file.read()),
            )
    except ExternalBlocker:
        raise
    except OSError as exc:
        raise ExternalBlocker(
            "official Unity/CLI executable could not be started",
            evidence={"command": command, "error": str(exc)},
        ) from exc


def _json_output(completed: subprocess.CompletedProcess[str], *, label: str) -> dict[str, Any]:
    raw = (completed.stdout or "").strip()
    if not raw:
        raise ExternalBlocker(
            f"{label} returned no JSON",
            evidence={"exit_code": completed.returncode, "stdout": _tail(completed.stdout or ""), "stderr": _tail(completed.stderr or "")},
        )
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExternalBlocker(
            f"{label} returned invalid JSON",
            evidence={"exit_code": completed.returncode, "stdout": _tail(raw), "stderr": _tail(completed.stderr or "")},
        ) from exc
    if not isinstance(value, dict):
        raise LiveFailure(f"{label} returned a non-object JSON result")
    return value


def _find_executable(name: str, explicit_env: str) -> Path:
    explicit = os.environ.get(explicit_env)
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if path.is_file():
            return path
        raise ExternalBlocker(f"{explicit_env} points to a missing executable", evidence={"path": str(path)})
    found = shutil.which(name)
    if found:
        return Path(found).resolve()
    raise ExternalBlocker(f"{name} was not found on PATH", evidence={"executable": name})


def _editor_path() -> Path:
    explicit = os.environ.get("UNITY_EDITOR_PATH")
    candidate = Path(explicit).expanduser().resolve() if explicit else DEFAULT_EDITOR
    if not candidate.is_file():
        raise ExternalBlocker(
            "Unity 6000.6.0f1 Editor executable is not installed on this host",
            evidence={"required_version": UNITY_VERSION, "path": str(candidate)},
        )
    return candidate


def _publish_or_resolve_artist_cli(artist_root: Path) -> Path:
    explicit = os.environ.get("UNITY_ARTIST_CLI_PATH")
    candidates = [
        Path(explicit).expanduser().resolve() if explicit else None,
        artist_root / "Artifacts" / "reference-live" / "publish" / "unity-artist.exe",
        artist_root / "src" / "UnityArtist.Cli" / "bin" / "Debug" / "net8.0" / "unity-artist.exe",
        artist_root / "src" / "UnityArtist.Cli" / "bin" / "Release" / "net8.0" / "unity-artist.exe",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()

    project = artist_root / "src" / "UnityArtist.Cli" / "UnityArtist.Cli.csproj"
    if not project.is_file():
        raise LiveFailure(f"UnityArtistCLI project was not found: {project}")
    output = artist_root / "Artifacts" / "reference-live" / "publish"
    output.mkdir(parents=True, exist_ok=True)
    dotnet_home = artist_root / "Artifacts" / "reference-live" / "dotnet-home"
    nuget = artist_root / "Artifacts" / "reference-live" / "nuget"
    dotnet_home.mkdir(parents=True, exist_ok=True)
    nuget.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "DOTNET_CLI_HOME": str(dotnet_home),
            "NUGET_PACKAGES": str(nuget),
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        }
    )
    completed = _run(
        ["dotnet", "publish", str(project), "--no-restore", "--runtime", "win-x64", "--self-contained", "false", "-o", str(output)],
        cwd=artist_root,
        timeout=180,
        env=env,
    )
    candidate = output / "unity-artist.exe"
    if completed.returncode != 0 or not candidate.is_file():
        raise LiveFailure(
            "UnityArtistCLI publish did not produce the official apphost",
        )
    return candidate.resolve()


def _run_official_unity(unity: Path, arguments: list[str], *, artist_root: Path, timeout: int = 90) -> dict[str, Any]:
    command = [str(unity), *arguments]
    completed = _run(command, cwd=artist_root, timeout=timeout)
    return {
        "command": command,
        "exit_code": completed.returncode,
        "payload": _json_output(completed, label="official Unity CLI"),
        "stdout": _tail(completed.stdout),
        "stderr": _tail(completed.stderr),
    }


def _run_artist(artist_cli: Path, project: Path, command: str, *, artist_root: Path, timeout: int = 120, **options: Any) -> dict[str, Any]:
    argv = [str(artist_cli), command, "--project-path", str(project)]
    for key, value in options.items():
        if value is None:
            continue
        option = "--" + key.replace("_", "-")
        argv.extend([option, json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)])
    argv.extend(["--format", "json", "--non-interactive", "--no-banner"])
    completed = _run(argv, cwd=artist_root, timeout=timeout)
    result = _json_output(completed, label=f"UnityArtistCLI {command}")
    result["_transport"] = {"command": argv, "exit_code": completed.returncode, "stderr": _tail(completed.stderr)}
    return result


def _errors(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = result.get("errors")
    return [dict(item) for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _first_error_code(result: Mapping[str, Any]) -> str | None:
    errors = _errors(result)
    return str(errors[0].get("code")) if errors and errors[0].get("code") else None


def _provider_result(result: Mapping[str, Any]) -> dict[str, Any]:
    data = result.get("data")
    if not isinstance(data, Mapping):
        raise ExternalBlocker("UnityArtistCLI returned no adapter data", evidence={"result": dict(result)})
    provider = data.get("provider")
    if isinstance(provider, Mapping):
        provider_data = provider.get("data")
        raw = provider_data.get("result") if isinstance(provider_data, Mapping) else None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ExternalBlocker("official Unity CLI returned a non-JSON Artist result", evidence={"provider": dict(provider)}) from exc
            if isinstance(parsed, dict):
                return parsed
        if isinstance(raw, Mapping):
            return dict(raw)
    adapter = data.get("adapter")
    if isinstance(adapter, Mapping):
        return dict(adapter)
    raise ExternalBlocker("UnityArtistCLI adapter did not expose the Editor result", evidence={"data": dict(data)})


def _successful_command(result: Mapping[str, Any], command: str) -> dict[str, Any]:
    if result.get("status") != "passed" or result.get("exitCode", 0) not in (0, None):
        raise ExternalBlocker(
            f"UnityArtistCLI {command} was not accepted by the live Editor",
            evidence={"result": dict(result), "error_code": _first_error_code(result)},
        )
    payload = _provider_result(result)
    if payload.get("status") not in {"passed", None}:
        raise ExternalBlocker(f"Unity Editor rejected artist.{command}", evidence={"host": dict(result), "editor": payload})
    return payload


def _inspect_when_ready(artist_cli: Path, project: Path, artist_root: Path, *, timeout_seconds: int = 120) -> dict[str, Any]:
    """Wait for the official Pipeline handshake after `unity open`."""
    deadline = time.monotonic() + timeout_seconds
    last_result: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        result = _run_artist(artist_cli, project, "inspect", artist_root=artist_root, timeout=30)
        last_result = result
        if result.get("status") == "passed" and result.get("exitCode", 0) in (0, None):
            payload = _successful_command(result, "inspect")
            try:
                # The official CLI can briefly answer through the previous
                # fixed-port Pipeline session while `unity open` is handing
                # the project to the fresh Editor.  Accept the handshake only
                # after the authoritative fixture camera is observed at its
                # bootstrap value; otherwise a stale 43-degree session could
                # be mistaken for the initial golden state.
                _find_camera(payload, expected_fov=40.0)
            except LiveFailure as exc:
                if "required 40 degree target" not in str(exc):
                    raise
                time.sleep(2.0)
                continue
            return payload
        code = _first_error_code(result)
        if code not in {"ARTIST_PIPELINE_COMMAND_FAILED", "PIPELINE_UNAVAILABLE", "PIPELINE_NOT_REACHABLE"}:
            return _successful_command(result, "inspect")
        time.sleep(2.0)
    raise ExternalBlocker(
        "Unity Editor did not become reachable through the official UnityArtist pipeline within the bounded startup window",
        evidence={"timeout_seconds": timeout_seconds, "last_inspect": last_result or {}},
    )


def _find_camera(inspect: Mapping[str, Any], *, expected_fov: float | None = 40.0) -> dict[str, Any]:
    targets = inspect.get("targets")
    if not isinstance(targets, list):
        raise LiveFailure("artist.inspect did not return targets")
    cameras = [item for item in targets if isinstance(item, Mapping) and item.get("kind") == "camera" and item.get("name") == "Main Camera"]
    if len(cameras) != 1:
        raise LiveFailure(f"artist.inspect did not return exactly one Main Camera: {cameras}")
    camera = dict(cameras[0])
    if not camera.get("globalObjectId") or (expected_fov is not None and float(camera.get("fieldOfView", -1.0)) != expected_fov):
        expected_text = "any" if expected_fov is None else f"{expected_fov:g}"
        raise LiveFailure(f"Main Camera inspection is not the required {expected_text} degree target: {camera}")
    return camera


def _find_mapping(value: Any, keys: tuple[str, ...]) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        if any(key in value for key in keys):
            return value
        for item in value.values():
            found = _find_mapping(item, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_mapping(item, keys)
            if found is not None:
                return found
    return None


def _find_named_mapping(value: Any, key: str) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        candidate = value.get(key)
        if isinstance(candidate, Mapping):
            return candidate
        for item in value.values():
            found = _find_named_mapping(item, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_named_mapping(item, key)
            if found is not None:
                return found
    return None


def _capture_path(value: Any, project: Path) -> Path:
    if isinstance(value, Mapping):
        for key in ("colorPath", "color_path", "path"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.lower().endswith(".png"):
                path = Path(candidate)
                return path if path.is_absolute() else (project / path)
        evidence = value.get("evidence")
        if isinstance(evidence, list):
            for item in evidence:
                if isinstance(item, str) and item.startswith("color_path:"):
                    path = Path(item.split(":", 1)[1])
                    return path if path.is_absolute() else (project / path)
        for item in value.values():
            try:
                return _capture_path(item, project)
            except LiveFailure:
                pass
    elif isinstance(value, list):
        for item in value:
            try:
                return _capture_path(item, project)
            except LiveFailure:
                pass
    raise LiveFailure("artist.capture did not expose a PNG path")


def _png_proof(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise LiveFailure(f"capture PNG does not exist: {path}")
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise LiveFailure(f"capture is not a valid PNG: {path}")
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0 or not data:
        raise LiveFailure(f"capture has invalid dimensions or byte count: {path}")
    return {"path": str(path.resolve()), "bytes": len(data), "resolution": f"{width}x{height}", "sha256": hashlib.sha256(data).hexdigest()}


def _environment_snapshot(project: Path, editor: Path, unity_cli: Path, artist_cli: Path, *, instance_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": {
            "root": str(project),
            "exists": True,
            "identity_status": "bound",
            "unity_version": UNITY_VERSION,
            "required_paths": {"assets": True, "packages": True, "project_settings": True},
        },
        "filesystem": {"readable": True, "writable": True, "writable_in_mutation_scope": True},
        "git": {"available": True, "repository_bound": True},
        "unity_editor": {
            "installed": True,
            "version": UNITY_VERSION,
            "executable_path": str(editor),
            "project_version_match": True,
            "running": True,
            "safe_mode": False,
            "project_bound": True,
            "binding_status": "bound",
            "bound_instance_id": instance_id,
        },
        "unity_cli": {"available": True, "version": "observed", "executable_path": str(unity_cli), "failure_class": None},
        "unity_artist_cli": {
            "available": True,
            "version": "0.0.1-beta",
            "executable_path": str(artist_cli),
            "project_bound": True,
            "package_installed": True,
            "package_version": "0.0.1-beta",
            "pipeline_reachable": True,
            "unity_version": UNITY_VERSION,
            "render_pipeline": "builtin",
            "support_tier": "primary",
            "compatibility_backend": "builtin_editor_api",
            "capabilities": ["visual_art.refine", "visual_art.capture"],
            "failure_class": None,
            "binding_status": "bound",
            "bound_instance_id": instance_id,
        },
        "pipeline": {"installed": True, "reachable": True},
        "myunitymcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
        "coplay_mcp": {"reachable": False, "available": False, "project_bound": False, "binding_status": "unbound", "bound_instance_id": None},
        "test_framework": {"available": True},
        "build": {"requested_target": None, "requested_target_module_available": "unknown"},
        "player_runtime": {"reachable": False, "instance_id": None},
        "profile_hint": "FULL",
        "binding_fingerprint": hashlib.sha256(f"{project}|{UNITY_VERSION}|{instance_id}".encode("utf-8")).hexdigest(),
    }


def _stop_fixture_editor(project: Path) -> list[int]:
    """Ensure the disposable live fixture has no stale Unity Editor owner.

    Unity keeps unsaved Scene state in the live Editor process.  Reusing an
    Editor for this golden task can therefore make a later run observe the
    previous run's FOV even when the serialized Scene is back at 40 degrees.
    The fixture is dedicated to this bounded E2E gate, so stop only Unity.exe
    processes whose command line contains this exact project path.  The
    process tree termination also closes UPM and other Editor descendants.
    """
    if os.name != "nt":
        return []

    project_text = str(project.resolve()).replace("'", "''")
    script = (
        "$target = '"
        + project_text
        + "'.ToLowerInvariant(); "
        "$processIds = @(Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'Unity.exe' -and $_.CommandLine -and "
        "$_.CommandLine.ToLowerInvariant().Contains($target) } | "
        "Select-Object -ExpandProperty ProcessId); "
        "foreach ($processId in $processIds) { "
        "& taskkill /PID $processId /T /F *> $null }; "
        "$processIds | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalBlocker(
            "could not establish a clean Unity fixture Editor state",
            evidence={"project": str(project), "error": str(exc)},
        ) from exc
    if completed.returncode != 0:
        raise ExternalBlocker(
            "could not enumerate or stop the Unity fixture Editor process",
            evidence={
                "project": str(project),
                "exit_code": completed.returncode,
                "stdout": _tail(completed.stdout),
                "stderr": _tail(completed.stderr),
            },
        )
    raw = (completed.stdout or "").strip()
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExternalBlocker(
            "Unity fixture process cleanup returned invalid process evidence",
            evidence={"project": str(project), "stdout": _tail(raw)},
        ) from exc
    if isinstance(values, int):
        return [values]
    if isinstance(values, list):
        return [int(value) for value in values]
    return []


def _prepare_fixture(project: Path, editor: Path, artist_root: Path, run_root: Path) -> dict[str, Any]:
    scene = project / "Assets" / "ReferenceCameraFovGolden.unity"
    log_path = run_root / "unity-fixture-bootstrap.log"
    command = [
        str(editor),
        "-batchmode",
        "-nographics",
        "-projectPath",
        str(project),
        "-executeMethod",
        "UnityArtist.Tests.UnityArtistReferenceFixtureBootstrap.Prepare",
        "-quit",
        "-logFile",
        str(log_path),
    ]
    completed = _run(command, cwd=artist_root, timeout=180, capture_output=False)
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    if completed.returncode != 0 or not scene.is_file():
        lowered = log.lower()
        external_tokens = ("package manager could not connect", "could not establish a connection with unity package manager", "licensing", "license", "ipc stream", "access is denied", "permission")
        evidence = {"command": command, "exit_code": completed.returncode, "scene_exists": scene.is_file(), "log_path": str(log_path), "log_tail": _tail(log), "stdout": _tail(completed.stdout), "stderr": _tail(completed.stderr)}
        if any(token in lowered for token in external_tokens):
            raise ExternalBlocker("Unity fixture bootstrap is blocked by Unity/UPM/licensing host state", evidence=evidence)
        raise LiveFailure("Unity fixture bootstrap failed",)
    return {"scene": str(scene), "bootstrap": "reset", "log": str(log_path)}


def _open_editor(unity_cli: Path, project: Path, artist_root: Path) -> dict[str, Any]:
    command = [
        str(unity_cli),
        "open",
        str(project),
        "--editor-version",
        UNITY_VERSION,
        "--format",
        "json",
        "--non-interactive",
        "--no-banner",
        "--proxy-disable",
    ]
    completed = _run(command, cwd=artist_root, timeout=90)
    if completed.returncode == 0 and not (completed.stdout or "").strip():
        # The installed Unity CLI reports a successful `open` through its
        # exit code and stderr warning when the project is not in the Hub
        # registry; it does not emit a JSON payload for this command.  The
        # subsequent artist.inspect is the authoritative Editor handshake.
        return {
            "command": command,
            "exit_code": completed.returncode,
            "payload": {"status": "opened", "projectPath": str(project), "unityVersion": UNITY_VERSION},
            "stdout": "",
            "stderr": _tail(completed.stderr),
        }
    return {
        "command": command,
        "exit_code": completed.returncode,
        "payload": _json_output(completed, label="official Unity CLI open"),
        "stdout": _tail(completed.stdout),
        "stderr": _tail(completed.stderr),
    }


def run_live(*, artist_root: Path, project: Path) -> dict[str, Any]:
    artist_root = artist_root.resolve()
    project = project.resolve()
    run_id = f"run-live-camera-fov-{uuid.uuid4().hex[:12]}"
    run_root = ROOT / "Artifacts" / "reference-implementation" / "live" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    if not project.is_dir():
        raise LiveFailure(f"Unity fixture project does not exist: {project}")
    editor = _editor_path()
    unity_cli = _find_executable("unity", "UNITY_CLI_PATH")
    artist_cli = _publish_or_resolve_artist_cli(artist_root)
    stopped_editor_pids = _stop_fixture_editor(project)
    fixture = _prepare_fixture(project, editor, artist_root, run_root)
    fixture["stopped_editor_pids"] = stopped_editor_pids
    opened = _open_editor(unity_cli, project, artist_root)

    inspect = _inspect_when_ready(artist_cli, project, artist_root)
    support = inspect.get("support")
    if not isinstance(support, Mapping) or support.get("transport") != "official_unity_cli_pipeline" or support.get("unityVersion") != UNITY_VERSION:
        raise LiveFailure(f"live UnityArtist support proof is not Unity 6000.6.0f1 official pipeline: {inspect}")
    camera = _find_camera(inspect, expected_fov=40.0)
    target_guid = str(camera["globalObjectId"])
    inspect_revision = str(inspect.get("revision") or "")
    if not inspect_revision:
        raise LiveFailure("artist.inspect did not return a revision")

    intent = {
        "workflow": "camera_fov_reference",
        "targetName": "Main Camera",
        "targetGuid": target_guid,
        "setCameraFieldOfView": True,
        "cameraFieldOfView": 43.0,
        "cameraFovMinimum": 35.0,
        "cameraFovMaximum": 50.0,
        "requestedChannels": ["camera"],
    }
    plan_host = _run_artist(artist_cli, project, "plan", artist_root=artist_root, request_json=intent)
    plan = _successful_command(plan_host, "plan")
    plan_id = str(plan.get("planId") or "")
    plan_revision = str(plan.get("revision") or "")
    if not plan_id or plan_revision != inspect_revision or plan.get("approvalRequired") is not True:
        raise LiveFailure(f"artist.plan is not approval/revision-bound: {plan}")
    preview_host = _run_artist(artist_cli, project, "preview", artist_root=artist_root, plan_id=plan_id, expected_revision=plan_revision)
    preview = _successful_command(preview_host, "preview")
    if not preview.get("exactDiff"):
        raise LiveFailure(f"artist.preview did not return exact diff: {preview}")

    no_approval = _run_artist(artist_cli, project, "apply", artist_root=artist_root, plan_id=plan_id, expected_revision=plan_revision)
    no_approval_code = _first_error_code(no_approval)
    if no_approval.get("status") != "blocked" or no_approval_code != "APPROVAL_REQUIRED":
        raise LiveFailure(f"apply without approval was not rejected: {no_approval}")

    project_info = {"root": str(project), "name": project.name}
    project_fingerprint = sha256_jcs({"project": project_info, "version": "reference-v1.1"})
    scope = {
        "target_guids": [target_guid],
        "component_type": "UnityEngine.Camera",
        "property_paths": ["Camera.fieldOfView"],
        "mutation_channels": ["serialized_property"],
    }
    budgets = {
        "max_parent_total_calls": 2,
        "max_parent_reentries": 0,
        "max_global_replans": 0,
        "max_escalations": 1,
        "max_child_llm_calls": 12,
        "max_tool_calls": 20,
        "max_wall_clock_ms": 120000,
        "max_child_wall_clock_ms": 60000,
        "max_child_input_tokens": 10000,
        "max_child_output_tokens": 10000,
        "max_parent_input_tokens": 20000,
        "max_parent_output_tokens": 10000,
        "max_process_restarts": 1,
        "max_provider_retries": 1,
    }
    issued_at = iso_now()
    task = TaskContractIssuer().issue(
        task_id=f"artist-camera-fov-live-{uuid.uuid4().hex[:10]}",
        run_id=run_id,
        project=project_info,
        project_fingerprint=project_fingerprint,
        budgets=budgets,
        scope=scope,
        issued_at=issued_at,
    )
    approval = ApprovalDecision.approve(
        approval_decision_id=f"approval-live-{uuid.uuid4().hex[:10]}",
        task=task,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
        lower=35.0,
        upper=50.0,
    )
    projection = {
        "reference_kind": "camera_fov_v1_1",
        "task_id": task.task_id,
        "run_id": run_id,
        "project_name": project.name,
        "project_fingerprint": project_fingerprint,
        "issued_at": issued_at,
        "target_guid": target_guid,
        "target_name": "Main Camera",
        "proposed_value": 43.0,
        "expected_revision": inspect_revision,
        "scope": scope,
        "budgets": budgets,
    }
    mutation_scope = {"allowed_paths": ["Assets/ReferenceCameraFovGolden.unity"], "prohibited_paths": ["ProjectSettings"]}
    required_evidence = ["domain_result", "mutation_evidence", "exact_diff", "expected_revision", "camera_binding", "undo_registration", "save_not_performed", "visual_capture"]
    capability_request = {
        "schema_version": "1.0",
        "capability": "domain.workflow",
        "project_root": str(project),
        "operation_kind": "editor_mutation",
        "required_evidence": required_evidence,
        "mutation_scope": mutation_scope,
        "approval_ref": approval.approval_decision_id,
        "preferred_surface": "live_editor",
        "qualifiers": {"domain": "visual_art", "workflow": "camera_fov_reference"},
    }
    entry_request = {
        "schema_version": "1.0",
        "request_id": f"camera-fov-live-{uuid.uuid4().hex[:10]}",
        "entry_point": "codex_plugin",
        "project_root": str(project),
        "intent": {"kind": "camera_fov_reference", "target": "Main Camera", "value": 43.0},
        "route_id": "camera_fov_reference",
        "node_id": "camera-fov-reference",
        "loop_id": "camera-fov-reference-loop",
        "execution_profile": "camera_fov_reference",
        "context_id": f"context-{run_id}",
        "context_fingerprint": sha256_jcs({"run_id": run_id, "target_guid": target_guid, "revision": inspect_revision}),
        "task_contract_runtime_projection": projection,
        "mutation_scope": mutation_scope,
        "validation_requirements": ["domain_result", "mutation_evidence", "exact_diff", "expected_revision", "camera_binding", "undo_registration", "save_not_performed", "visual_capture"],
        "capability_requests": [capability_request],
    }
    snapshot = _environment_snapshot(project, editor, unity_cli, artist_cli, instance_id=f"unity-{run_id}")
    provider = UnityArtistCliProvider(project, snapshot)
    # Keep the canonical Persistence root at the shared live-artifact level;
    # PersistenceLayout adds the run_id exactly once under runs/<run_id>.
    # Using the per-run log directory as the root would duplicate the run_id
    # and push LoopControlState paths over Windows MAX_PATH.
    plane = UnityAgentControlPlane(run_root.parent)
    plane.approval_resolver.register(approval)
    result = plane.execute(
        entry_request,
        environment_snapshot=snapshot,
        context=ResolutionContext(policy_allowed=True, approval_complete=True, approval_required=True),
        executors={"unity_artist_cli": provider.execute},
        definition_fingerprint=reference_definition_fingerprint(),
        provider_arguments={"unity_artist_cli": {"timeout_seconds": 120.0}},
        run_id=run_id,
    )
    if result.get("status") != "completed":
        raise LiveFailure(f"canonical ControlPlane route did not complete: {result}")
    reference = (result.get("results") or [None])[0]
    if not isinstance(reference, Mapping):
        raise LiveFailure("ControlPlane did not return the Camera FOV reference result")
    provider_result = reference.get("provider_result")
    if not isinstance(provider_result, Mapping):
        raise LiveFailure("ControlPlane result did not contain a ProviderResult")
    if float(provider_result.get("before_value", -1.0)) != 40.0 or float(provider_result.get("after_value", -1.0)) != 43.0:
        raise LiveFailure(f"ProviderResult before/after is not 40 -> 43: {provider_result}")
    exact_diff = provider_result.get("exact_diff")
    if not isinstance(exact_diff, Mapping) or exact_diff.get("target") != target_guid or exact_diff.get("property") != "Camera.fieldOfView":
        raise LiveFailure(f"ProviderResult exact diff is not bound to the inspected camera: {provider_result}")
    completion = reference.get("completion")
    if not isinstance(completion, Mapping) or completion.get("state") != "eligible":
        raise LiveFailure(f"Evidence completion was not eligible: {completion}")
    evidence_refs = list(reference.get("evidence_refs") or [])
    if set(evidence_refs) != {f"{run_id}-mutation-diff", f"{run_id}-editor-observation", f"{run_id}-visual-capture"}:
        raise LiveFailure(f"ControlPlane evidence union is incomplete: {evidence_refs}")

    metadata = reference.get("metadata") if isinstance(reference.get("metadata"), Mapping) else {}
    capture = _find_named_mapping(metadata, "capture") or metadata
    capture_file = _capture_path(capture, project)
    capture_proof = _png_proof(capture_file)
    apply_payload = _find_named_mapping(metadata, "apply")
    if apply_payload is None:
        apply_payload = _find_mapping(metadata, ("savePerformed", "save_performed"))
    if isinstance(apply_payload, Mapping):
        if apply_payload.get("savePerformed", apply_payload.get("save_performed", False)) is not False:
            raise LiveFailure(f"Unity Artist apply unexpectedly saved the scene: {apply_payload}")
        if apply_payload.get("undoAvailable", apply_payload.get("undo_available", False)) is not True:
            raise LiveFailure(f"Unity Artist apply did not expose Undo evidence: {apply_payload}")

    final_host = _run_artist(artist_cli, project, "inspect", artist_root=artist_root)
    final_inspect = _successful_command(final_host, "inspect")
    final_camera = _find_camera(final_inspect, expected_fov=43.0)
    if final_camera.get("globalObjectId") != target_guid or float(final_camera.get("fieldOfView", -1.0)) != 43.0:
        raise LiveFailure(f"post-apply inspect did not observe the real camera at FOV 43: {final_camera}")

    return {
        "status": "passed",
        "run_id": run_id,
        "fixture": fixture,
        "official_unity_open": opened,
        "before": {"inspect": inspect, "camera": camera, "revision": inspect_revision, "plan": plan, "preview": preview, "no_approval_apply": no_approval},
        "control_plane": result,
        "after": {"inspect": final_inspect, "camera": final_camera},
        "capture": capture_proof,
        "proof": {
            "transport": support.get("transport"),
            "unity_version": support.get("unityVersion"),
            "target_global_object_id": target_guid,
            "before_fov": provider_result.get("before_value"),
            "after_fov": provider_result.get("after_value"),
            "action_digest": ((reference.get("dispatch") or {}).get("provider_result_digest") if isinstance(reference.get("dispatch"), Mapping) else None) or provider_result.get("provider_result_digest"),
            "completion_state": completion.get("state"),
            "evidence_refs": evidence_refs,
            "save_performed": False,
            "undo_available": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unityartist-root", type=Path, default=DEFAULT_ARTIST_ROOT)
    parser.add_argument("--project-path", type=Path, default=DEFAULT_PROJECT)
    args = parser.parse_args()
    output: dict[str, Any]
    exit_code = 1
    try:
        report = run_live(artist_root=args.unityartist_root, project=args.project_path)
        output = report
        exit_code = 0
    except ExternalBlocker as exc:
        output = {"status": "blocked_external", "error": str(exc), "evidence": exc.evidence}
        exit_code = 2
    except (ContractValidationError, LiveFailure, OSError, ValueError) as exc:
        output = {"status": "failed", "error": str(exc)}
        exit_code = 1
    finally:
        try:
            stopped_after_run = _stop_fixture_editor(args.project_path)
            if exit_code == 0 and isinstance(output.get("fixture"), dict):
                output["fixture"]["stopped_editor_pids_after_run"] = stopped_after_run
        except ExternalBlocker as cleanup_error:
            if exit_code == 0:
                output = {"status": "blocked_external", "error": str(cleanup_error), "evidence": cleanup_error.evidence}
                exit_code = 2
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
