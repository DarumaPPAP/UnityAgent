"""Run the Camera FOV reference route against a real Unity Editor.

This runner is deliberately a gate/orchestration harness. The mutation itself is
still owned by the canonical src/unityagent/control_plane -> ToolBroker -> Provider -> Evidence
chain; this module never edits Unity YAML and never invokes a Provider's
subprocess transport directly. Fixture bootstrap is opt-in; a real project can
provide an existing scene through ``--scene-path``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
DEFAULT_ARTIST_ROOT = ROOT
DEFAULT_PROJECT = DEFAULT_ARTIST_ROOT / "tests" / "unity" / "projects" / "artist-e2e"
DEFAULT_SCENE_PATH = "Assets/ReferenceCameraFovGolden.unity"
UNITY_VERSION = "6000.6.0f1"
DEFAULT_EDITOR = Path("C:/Program Files/Unity/Hub/Editor/6000.6.0f1/Editor/Unity.exe")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.control_plane.artist_execution import execute_artist, approve_artist_execution
from unityagent.persistence.evidence.evidence_store import EvidenceStore
from unityagent.persistence.store.atomic_store import read_json, safe_id, sha256_json, write_immutable_json
from unityagent.runtime.reference_implementation.contracts import ContractValidationError
from unityagent.runtime.reference_implementation.runtime import reference_definition_fingerprint
from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand
from unityagent.runtime.tooling.environment.project_identity import canonical_scene_path, same_project_root



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

        # The official Unity CLI can launch Editor/UPM
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


def _successful_command(result: Mapping[str, Any], command: str) -> dict[str, Any]:
    provider = result.get("provider_result") or {}
    payload = provider.get("payload") or {}
    if result.get("status") != "completed" or result.get("durable") is not True or not result.get("evidence_refs") or provider.get("status") != "passed" or provider.get("provider_ref") != "unity_cli" or payload.get("status") != "passed" or payload.get("command") != "artist." + command:
        raise ExternalBlocker(f"Control Plane artist.{command} did not produce verified durable Editor evidence", evidence={"result": dict(result)})
    return dict(payload)


def _execute(plane, project, run_id, command, **options):
    return execute_artist(plane, str(project), run_id, command, definition_fingerprint=reference_definition_fingerprint(), **options)


def _inspect_when_ready(plane, project: Path, run_id: str, *, expected_fov: float | None = 40.0, timeout_seconds: int = 120, scope=None) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last = {}
    while time.monotonic() < deadline:
        try:
            result = _execute(plane, project, run_id, ArtistCommand("inspect"), scope=scope)
            payload = _successful_command(result, "inspect")
            _find_camera(payload, expected_fov=expected_fov)
            return result
        except (ExternalBlocker, ValueError) as exc:
            last = {"error": str(exc), "evidence": getattr(exc, "evidence", {})}
        time.sleep(2.0)
    raise ExternalBlocker("Unity Editor did not become reachable through the verified Unity CLI Artist route", evidence={"timeout_seconds": timeout_seconds, "last_inspect": last})


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
        "$target = '" + project_text + "'; "
        "$escaped = [regex]::Escape($target); "
        "$targetPattern = '(?i)(?:^|\\s)-projectPath\\s+(?:"' + $escaped + '"|' + $escaped + '(?=\\s|$))'; "
        "$processIds = @(Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'Unity.exe' -and $_.CommandLine -and "
        "$_.CommandLine -match $targetPattern } | "
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


def _open_scene(unity_cli: Path, project: Path, artist_root: Path, scene_path: str) -> dict[str, Any]:
    """Open an existing scene through the official Pipeline command."""
    scene_path = canonical_scene_path(project, scene_path, require_exists=True)
    command = [
        str(unity_cli),
        "command",
        "open_scene",
        "--project-path",
        str(project),
        "--path",
        scene_path,
        "--timeout",
        "60",
        "--format",
        "json",
        "--non-interactive",
        "--no-banner",
    ]
    completed = _run(command, cwd=artist_root, timeout=90)
    payload = _json_output(completed, label="official Unity CLI open_scene")
    data = payload.get("data")
    result = data.get("result") if isinstance(data, Mapping) else None
    if completed.returncode != 0 or payload.get("success") is not True or not isinstance(data, Mapping) or data.get("success") is not True or not isinstance(result, Mapping):
        raise ExternalBlocker(
            "official Unity CLI could not open the requested live scene",
            evidence={"command": command, "exit_code": completed.returncode, "payload": payload},
        )
    return {"command": command, "exit_code": completed.returncode, "payload": payload}


def _source_fingerprint() -> str:
    sources = {}
    for base in (ROOT / "src/unityagent", ROOT / "subagent/artist_subagent/tools/editor"):
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".cs", ".yaml", ".json", ".asmdef"} and not {"_resources", "__pycache__", "bin", "obj"}.intersection(path.relative_to(base).parts):
                sources[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("tools/run_camera_fov_reference_live.py", "tools/reference_implementation_final_gate.py"):
        sources[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return sha256_json(sources)


def _persisted_payload(store, result, run_id, project, command):
    expected = _successful_command(result, command)
    for evidence_id in result["evidence_refs"]:
        record = store.verify_record(evidence_id, expected_run_id=run_id)
        if record.get("durability") != "durable" or record.get("verification_status") != "passed" or record.get("provider_ref") != "unity_cli" or not same_project_root(record.get("project_root", ""), project):
            raise LiveFailure("persisted Artist evidence is not verified for the selected Project")
        reference = record.get("payload_ref")
        path = (store.layout.root / str(reference)).resolve()
        if not reference or Path(reference).is_absolute() or not path.is_relative_to(store.layout.run_root(run_id).resolve()):
            raise LiveFailure("persisted Artist provider payload escapes this Run")
        raw = read_json(path)
        if path.stem != sha256_json(raw).removeprefix("sha256:") or raw.get("payload") != expected or raw.get("provider_ref") != "unity_cli":
            raise LiveFailure("persisted Artist provider payload digest or Editor result differs")
    return expected


def verify_live_evidence(*, run_id: str, persistence_root: Path, project_root: Path, scene_path: str, expected_before_fov: float, expected_after_fov: float = 43.0, _require_gate_record: bool = True, _report=None):
    run_id = safe_id(run_id, "run_id")
    store = EvidenceStore(persistence_root)
    report = _report if _report is not None and not _require_gate_record else read_json(store.layout.root / "artist-live-reports" / (run_id + ".json"))
    if report.get("status") != "passed" or report.get("run_id") != run_id or report.get("source_fingerprint") != _source_fingerprint() or not same_project_root(report.get("project_root", ""), project_root) or report.get("scene_path") != scene_path:
        raise LiveFailure("persisted live proof belongs to different sources, Project, Scene or Run")
    if _require_gate_record:
        gate_record = store.verify_record(run_id + "-live-gate", expected_run_id=run_id)
        if gate_record.get("source_type") != "live_gate_verification" or gate_record.get("verification_status") != "passed" or gate_record.get("hash") != sha256_json(report) or gate_record.get("provenance") != ["source_fingerprint:" + report["source_fingerprint"]]:
            raise LiveFailure("live report is not bound to durable verification evidence")
    scene = Path(project_root) / canonical_scene_path(project_root, scene_path, require_exists=True)
    if hashlib.sha256(scene.read_bytes()).hexdigest() != report["scene_file_sha256"]:
        raise LiveFailure("saved Scene changed since live verification")
    commands = report["command_results"]
    before = _persisted_payload(store, commands["inspect_before"], run_id, project_root, "inspect")
    planned = _persisted_payload(store, commands["plan"], run_id, project_root, "plan")
    preview = _persisted_payload(store, commands["preview"], run_id, project_root, "preview")
    applied = _persisted_payload(store, commands["apply"], run_id, project_root, "apply")
    capture = _persisted_payload(store, commands["capture"], run_id, project_root, "capture")
    after = _persisted_payload(store, commands["inspect_after"], run_id, project_root, "inspect")
    camera_before = _find_camera(before, expected_fov=expected_before_fov)
    camera_after = _find_camera(after, expected_fov=expected_after_fov)
    target = camera_before["globalObjectId"]
    expected_diff = [{"target": target, "property": "Camera.fieldOfView", "before": format(expected_before_fov, "g"), "after": format(expected_after_fov, "g")}]
    if camera_after["globalObjectId"] != target or any(item.get("exactDiff") != expected_diff for item in (planned, preview, applied)):
        raise LiveFailure("Camera FOV exact Diff or GlobalObjectId does not match the observed Plan")
    if planned.get("planId") != applied.get("planId") or applied.get("baseRevision") != planned.get("revision") or applied.get("revision") != after.get("revision") or applied.get("revision") == applied.get("baseRevision"):
        raise LiveFailure("Camera FOV revision or Plan chain is not verified")
    if applied.get("savePerformed") is not False or applied.get("undoAvailable") is not True or applied.get("verified") is not True or not applied.get("authorityReservationId") or not applied.get("authoritySessionId"):
        raise LiveFailure("Camera FOV approval, Undo or non-save evidence is missing")
    if commands["apply"].get("context_fingerprint") != commands["inspect_before"].get("context_fingerprint"):
        raise LiveFailure("Camera FOV Context changed during execution")
    capture_proof = _png_proof(_capture_path(capture, Path(project_root)))
    if capture_proof != report["capture"]:
        raise LiveFailure("Capture bytes changed since verification")
    return {"status": "passed", "verification_kind": "persisted_live_evidence_revalidation", "run_id": run_id, "before_fov": expected_before_fov, "after_fov": expected_after_fov, "evidence_refs": [ref for result in commands.values() for ref in result["evidence_refs"]], "capture": capture_proof, "source_fingerprint": report["source_fingerprint"], "live_editor_rerun": "not_observed"}


def run_live(*, artist_root: Path, project: Path, scene_path: str | None = None, expected_before_fov: float = 40.0, run_id: str | None = None, state_root: Path | None = None, approval_ref: str | None = None, approve_fixture_mutation: bool = False) -> dict[str, Any]:
    artist_root, project = artist_root.resolve(), project.resolve()
    selected_scene = str(scene_path or "").strip().replace("\\", "/") or None
    if approve_fixture_mutation and (selected_scene is not None or project != DEFAULT_PROJECT.resolve()):
        raise LiveFailure("fixture approval is limited to the repository-owned disposable fixture")
    if selected_scene is None and project != DEFAULT_PROJECT.resolve():
        raise LiveFailure("fixture bootstrap requires the repository-owned disposable fixture; pass an existing scene explicitly")
    run_id = safe_id(run_id or "run-live-camera-fov-" + uuid.uuid4().hex[:12], "run_id")
    state_root = (state_root or ROOT / "Artifacts/reference-implementation/live").resolve()
    run_root = state_root / "artist-live-logs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    plane = UnityAgentControlPlane(state_root)
    if not project.is_dir():
        raise LiveFailure(f"Unity live project does not exist: {project}")
    editor = _editor_path()
    unity_cli = _find_executable("unity", "UNITY_CLI_PATH")
    scope = {"allowed_paths": [selected_scene or DEFAULT_SCENE_PATH], "prohibited_paths": ["Packages", "ProjectSettings"]}
    pending_path = state_root / "artist-live-pending" / (run_id + ".json")
    resuming = approval_ref is not None and pending_path.is_file()
    if resuming:
        pending = read_json(pending_path)
        if pending.get("source_fingerprint") != _source_fingerprint() or not same_project_root(pending.get("project_root", ""), project) or pending.get("scene_path") != (selected_scene or DEFAULT_SCENE_PATH) or pending.get("expected_before_fov") != expected_before_fov:
            raise LiveFailure("pending Camera Plan belongs to different sources, Project or Scene")
        setup, opened = pending["project_setup"], pending["official_unity_open"]
        before_result, planned_result, preview_result = pending["inspect_before"], pending["plan"], pending["preview"]
        scene_hash = pending["scene_file_sha256"]
        current = _successful_command(_inspect_when_ready(plane, project, run_id, expected_fov=expected_before_fov, scope=scope), "inspect")
        if current.get("revision") != _successful_command(planned_result, "plan").get("revision"):
            raise LiveFailure("Editor Revision changed after explicit Plan review")
    else:
        if selected_scene is None:
            stopped = _stop_fixture_editor(project)
            setup = _prepare_fixture(project, editor, artist_root, run_root)
            setup["stopped_editor_pids"] = stopped
        else:
            selected_scene = canonical_scene_path(project, selected_scene, require_exists=True)
            setup = {"mode": "existing_project", "scene_path": selected_scene, "bootstrap": "not_run"}
        opened = _open_editor(unity_cli, project, artist_root)
        if selected_scene is not None:
            setup["scene_open"] = _open_scene(unity_cli, project, artist_root, selected_scene)
        scene_hash = hashlib.sha256((project / (selected_scene or DEFAULT_SCENE_PATH)).read_bytes()).hexdigest()
        before_result = _inspect_when_ready(plane, project, run_id, expected_fov=expected_before_fov, scope=scope)
        inspect = _successful_command(before_result, "inspect")
        camera = _find_camera(inspect, expected_fov=expected_before_fov)
        intent = {"workflow": "camera_fov_reference", "targetName": "Main Camera", "targetGuid": camera["globalObjectId"], "setCameraFieldOfView": True, "cameraFieldOfView": 43.0, "cameraFovMinimum": 35.0, "cameraFovMaximum": 50.0, "requestedChannels": ["camera"]}
        planned_result = _execute(plane, project, run_id, ArtistCommand("plan", request_json=json.dumps(intent)))
        planned = _successful_command(planned_result, "plan")
        if not planned.get("planId") or planned.get("revision") != inspect.get("revision") or planned.get("approvalRequired") is not True:
            raise LiveFailure("artist.plan is not approval/revision-bound")
        preview_result = _execute(plane, project, run_id, ArtistCommand("preview", plan_id=planned["planId"], expected_revision=planned["revision"]))
        _successful_command(preview_result, "preview")
        pending = {"source_fingerprint": _source_fingerprint(), "project_root": str(project), "scene_path": selected_scene or DEFAULT_SCENE_PATH, "expected_before_fov": expected_before_fov, "scene_file_sha256": scene_hash, "project_setup": setup, "official_unity_open": opened, "inspect_before": before_result, "plan": planned_result, "preview": preview_result}
        write_immutable_json(pending_path, pending)
    scene = project / (selected_scene or DEFAULT_SCENE_PATH)
    inspect = _successful_command(before_result, "inspect")
    support = inspect.get("support") or {}
    if support.get("transport") != "official_unity_cli_pipeline":
        raise LiveFailure("Artist support did not identify the official Unity CLI Pipeline")
    camera = _find_camera(inspect, expected_fov=expected_before_fov)
    planned = _successful_command(planned_result, "plan")
    plan_id = planned["planId"]
    try:
        _execute(plane, project, run_id, ArtistCommand("apply", plan_id=plan_id))
    except ValueError:
        no_approval = {"status": "blocked", "reason": "explicit_plan_approval_required"}
    else:
        raise LiveFailure("Apply without explicit approval was not rejected")
    if approve_fixture_mutation:
        decision = approve_artist_execution(plane, str(project), run_id, planned_result["approval_plan_id"])
        approval_ref = decision["approval_decision_id"]
    if not approval_ref:
        raise ExternalBlocker("exact Camera FOV Plan requires explicit approval before Apply", evidence={"gate": "BLOCKED_NOT_RUN", "run_id": run_id, "state_root": str(state_root), "approval_plan_id": planned_result["approval_plan_id"], "plan": planned, "no_approval": no_approval})
    applied_result = _execute(plane, project, run_id, ArtistCommand("apply", plan_id=plan_id), approval_ref=approval_ref)
    _successful_command(applied_result, "apply")
    capture_result = _execute(plane, project, run_id, ArtistCommand("capture", request_json=json.dumps({"captureCameraName": "Main Camera"})))
    capture = _successful_command(capture_result, "capture")
    after_result = _execute(plane, project, run_id, ArtistCommand("inspect"))
    _successful_command(after_result, "inspect")
    if hashlib.sha256(scene.read_bytes()).hexdigest() != scene_hash:
        raise LiveFailure("Camera FOV live workflow unexpectedly saved the Scene")
    report = {"status": "passed", "run_id": run_id, "project_root": str(project), "scene_path": selected_scene or DEFAULT_SCENE_PATH, "source_fingerprint": _source_fingerprint(), "scene_file_sha256": scene_hash, "project_setup": setup, "official_unity_open": opened, "before": {"inspect": inspect, "camera": camera, "plan": planned, "no_approval_apply": no_approval}, "command_results": {"inspect_before": before_result, "plan": planned_result, "preview": preview_result, "apply": applied_result, "capture": capture_result, "inspect_after": after_result}, "capture": _png_proof(_capture_path(capture, project)), "human_visual_acceptance": "not_observed"}
    path = state_root / "artist-live-reports" / (run_id + ".json")
    proof = verify_live_evidence(run_id=run_id, persistence_root=state_root, project_root=project, scene_path=report["scene_path"], expected_before_fov=expected_before_fov, _require_gate_record=False, _report=report)
    write_immutable_json(path, report)
    plane.evidence_store.append({"schema_version": "1.0", "evidence_id": run_id + "-live-gate", "run_id": run_id, "step_id": "camera-fov-live-gate", "source_type": "live_gate_verification", "source_ref": path.relative_to(state_root).as_posix(), "timestamp": datetime.now(timezone.utc).isoformat(), "hash": sha256_json(report), "producer": "camera_fov_live_gate", "verification_status": "passed", "provenance": ["source_fingerprint:" + report["source_fingerprint"]], "definition_fingerprint": reference_definition_fingerprint()})
    return {**report, "proof": proof}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unityartist-root", type=Path, default=DEFAULT_ARTIST_ROOT)
    parser.add_argument("--project-path", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--scene-path", help="Existing Assets-relative scene path; omit to bootstrap the disposable reference fixture.")
    parser.add_argument("--expected-before-fov", type=float, default=40.0)
    parser.add_argument("--run-id")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--approval-ref")
    parser.add_argument("--approve-fixture-mutation", action="store_true", help="Explicitly approve only the repository-owned disposable test fixture Plan.")
    args = parser.parse_args()
    output: dict[str, Any]
    exit_code = 1
    try:
        report = run_live(
            artist_root=args.unityartist_root,
            project=args.project_path,
            scene_path=args.scene_path,
            expected_before_fov=args.expected_before_fov, run_id=args.run_id, state_root=args.state_root, approval_ref=args.approval_ref, approve_fixture_mutation=args.approve_fixture_mutation,
        )
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
            if exit_code == 0 and not args.scene_path and args.project_path.resolve() == DEFAULT_PROJECT.resolve():
                stopped_after_run = _stop_fixture_editor(args.project_path)
                if exit_code == 0 and isinstance(output.get("project_setup"), dict):
                    output["project_setup"]["stopped_editor_pids_after_run"] = stopped_after_run
        except ExternalBlocker as cleanup_error:
            if exit_code == 0:
                output = {"status": "blocked_external", "error": str(cleanup_error), "evidence": cleanup_error.evidence}
                exit_code = 2
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
