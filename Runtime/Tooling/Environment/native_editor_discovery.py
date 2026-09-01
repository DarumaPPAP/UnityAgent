"""Read-only native Unity Editor installation/process discovery and target binding."""
from __future__ import annotations

import json
import os
import platform
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from Runtime.Tooling.Environment.project_identity import same_project_root

MAX_EDITOR_CANDIDATES = 32
PROCESS_PROBE_TIMEOUT_SECONDS = 5.0
_PROJECT_PATH_RE = re.compile(r"(?:^|\s)-projectPath(?:=|\s+)(?:\"([^\"]+)\"|'([^']+)'|(\S+))", re.IGNORECASE)


@dataclass(frozen=True)
class EditorCandidate:
    executable_path: str
    version: str | None


@dataclass(frozen=True)
class EditorProcessObservation:
    pid: int
    executable_path: str | None
    command_line: str
    project_root: str | None = None
    safe_mode: bool | None = None

    @property
    def instance_id(self) -> str:
        return f"pid:{self.pid}"


def _version_from_editor_path(path: Path) -> str | None:
    parts = path.as_posix().split("/")
    lowered = [part.casefold() for part in parts]
    for index in range(len(parts) - 2):
        if lowered[index] == "hub" and lowered[index + 1] == "editor":
            return parts[index + 2]
    return None


def enumerate_native_editor_candidates(
    *,
    project_version: str | None,
    platform_name: str | None = None,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
) -> list[EditorCandidate]:
    """Enumerate bounded OS-native Unity Editor candidates, exact version first."""
    env = dict(os.environ if environ is None else environ)
    system = (platform_name or platform.system()).lower()
    home_path = (home or Path.home()).expanduser()
    paths: list[Path] = []

    explicit = env.get("UNITY_EDITOR_PATH")
    if explicit:
        paths.append(Path(explicit).expanduser())

    patterns: list[Path] = []
    if system.startswith("win"):
        program_files = Path(env.get("ProgramFiles", r"C:\Program Files"))
        base = program_files / "Unity/Hub/Editor"
        if project_version:
            paths.append(base / project_version / "Editor/Unity.exe")
        patterns.append(base)
    elif system == "darwin":
        base = Path("/Applications/Unity/Hub/Editor")
        if project_version:
            paths.append(base / project_version / "Unity.app/Contents/MacOS/Unity")
        patterns.append(base)
    else:
        for base in (home_path / "Unity/Hub/Editor", Path("/opt/unityhub/Editor")):
            if project_version:
                paths.append(base / project_version / "Editor/Unity")
            patterns.append(base)

    discovered: list[Path] = []
    for base in patterns:
        if not base.is_dir():
            continue
        version_dirs = sorted((item for item in base.iterdir() if item.is_dir()), key=lambda item: item.name, reverse=True)
        for version_dir in version_dirs[:MAX_EDITOR_CANDIDATES]:
            if system.startswith("win"):
                discovered.append(version_dir / "Editor/Unity.exe")
            elif system == "darwin":
                discovered.append(version_dir / "Unity.app/Contents/MacOS/Unity")
            else:
                discovered.append(version_dir / "Editor/Unity")

    unique: dict[str, EditorCandidate] = {}
    for path in [*paths, *discovered]:
        if not path.is_file():
            continue
        normalized = str(path.resolve(strict=False))
        unique.setdefault(normalized, EditorCandidate(normalized, _version_from_editor_path(path)))

    values = list(unique.values())
    values.sort(key=lambda item: (item.version == project_version, item.version or ""), reverse=True)
    return values[:MAX_EDITOR_CANDIDATES]


def _extract_project_path(command_line: str, *, platform_name: str | None = None) -> str | None:
    match = _PROJECT_PATH_RE.search(command_line)
    if match:
        return next((value for value in match.groups() if value), None)
    try:
        tokens = shlex.split(command_line, posix=not (platform_name or platform.system()).lower().startswith("win"))
    except ValueError:
        return None
    for index, token in enumerate(tokens[:-1]):
        if token.casefold() == "-projectpath":
            return tokens[index + 1]
    return None


def process_observation_from_row(
    *,
    pid: int,
    executable_path: str | None,
    command_line: str,
    platform_name: str | None = None,
) -> EditorProcessObservation:
    project_root = _extract_project_path(command_line, platform_name=platform_name)
    safe_mode = "-safemode" in command_line.casefold()
    return EditorProcessObservation(pid, executable_path, command_line, project_root, safe_mode)


def discover_editor_processes(
    *,
    cwd: Path,
    platform_name: str | None = None,
    dispatch_fn: Callable[..., dict] = dispatch,
) -> list[EditorProcessObservation] | None:
    """Return observed Unity Editor processes, or None when process facts are unavailable."""
    system = (platform_name or platform.system()).lower()
    if system.startswith("win"):
        command = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'Unity.exe'} | "
            "Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress",
        ]
        outcome = dispatch_fn(DispatchRequest(command, cwd, PROCESS_PROBE_TIMEOUT_SECONDS))
        if outcome.get("status") != "passed":
            return None
        raw = str(outcome.get("payload") or "").strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        rows = payload if isinstance(payload, list) else [payload]
        observations: list[EditorProcessObservation] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("ProcessId") is None:
                continue
            observations.append(
                process_observation_from_row(
                    pid=int(row["ProcessId"]),
                    executable_path=row.get("ExecutablePath"),
                    command_line=str(row.get("CommandLine") or ""),
                    platform_name=platform_name,
                )
            )
        return observations

    outcome = dispatch_fn(DispatchRequest(["ps", "-eo", "pid=,args="], cwd, PROCESS_PROBE_TIMEOUT_SECONDS))
    if outcome.get("status") != "passed":
        return None
    observations = []
    for line in str(outcome.get("payload") or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, separator, command_line = stripped.partition(" ")
        if not separator or not pid_text.isdigit():
            continue
        lowered = command_line.casefold()
        if "unity" not in lowered or ("/unity" not in lowered and "unity.app" not in lowered and "unity -" not in lowered):
            continue
        observations.append(
            process_observation_from_row(
                pid=int(pid_text),
                executable_path=None,
                command_line=command_line,
                platform_name=platform_name,
            )
        )
    return observations


def bind_editor_processes(
    target_project_root: str,
    processes: Sequence[EditorProcessObservation] | None,
    *,
    platform_name: str | None = None,
) -> dict:
    """Separate process discovery from exact target-project binding; ambiguity fails closed."""
    if processes is None:
        return {
            "running": "unknown",
            "safe_mode": "unknown",
            "project_bound": "unknown",
            "binding_status": "unknown",
            "bound_instance_id": None,
        }

    unity_processes = list(processes)
    if not unity_processes:
        return {
            "running": False,
            "safe_mode": "unknown",
            "project_bound": False,
            "binding_status": "not_running",
            "bound_instance_id": None,
        }

    matching = [
        item
        for item in unity_processes
        if item.project_root is not None
        and same_project_root(item.project_root, target_project_root, platform_name=platform_name)
    ]
    if len(matching) == 1:
        item = matching[0]
        return {
            "running": True,
            "safe_mode": item.safe_mode if item.safe_mode is not None else "unknown",
            "project_bound": True,
            "binding_status": "bound",
            "bound_instance_id": item.instance_id,
        }
    if len(matching) > 1:
        return {
            "running": True,
            "safe_mode": "unknown",
            "project_bound": False,
            "binding_status": "ambiguous_binding",
            "bound_instance_id": None,
        }
    return {
        "running": True,
        "safe_mode": "unknown",
        "project_bound": False,
        "binding_status": "unbound",
        "bound_instance_id": None,
    }
