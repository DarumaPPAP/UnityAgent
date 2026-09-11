"""Codex plugin observation and approved installation for UnityAgent.

This module is owned by the Installer Provider. Entry surfaces never invoke Codex
plugin commands directly; Unity UI and the Codex entry route setup requests
through the UnityAgent Control Plane first.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable, Mapping, Sequence

CHANNEL = "0.0.6-beta"
MARKETPLACE_SOURCE = "DarumaPPAP/UnityAgent"
MARKETPLACE_NAME = "unity-agent"
MARKETPLACE_REF = f"v{CHANNEL}"
PLUGIN_NAME = "unity-agent"
PLUGIN_ID = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"


class CodexPluginInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str]], CommandResult]


def _windows_command(arguments: Sequence[str]) -> list[str]:
    command = list(arguments)
    if not command:
        return command
    suffix = Path(command[0]).suffix.casefold()
    if os.name == "nt" and suffix in {".cmd", ".bat"}:
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        return [comspec, "/d", "/s", "/c", subprocess.list2cmdline(command)]
    if os.name == "nt" and suffix == ".ps1":
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            command[0],
            *command[1:],
        ]
    return command


def run_command(arguments: Sequence[str], *, timeout_seconds: float = 90.0) -> CommandResult:
    creationflags = 0
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = int(subprocess.CREATE_NO_WINDOW)
    command = _windows_command(arguments)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexPluginInstallError(
            f"Codex command could not run. Executable: {arguments[0] if arguments else '<missing>'}. Error: {exc}"
        ) from exc
    return CommandResult(completed.returncode, completed.stdout or "", completed.stderr or "")


def _json_output(result: CommandResult, command_name: str) -> Any:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise CodexPluginInstallError(f"{command_name} failed: {detail or f'exit code {result.returncode}'}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        detail = result.stdout.strip()
        if len(detail) > 240:
            detail = detail[:240] + "..."
        raise CodexPluginInstallError(
            f"{command_name} did not return valid JSON. Output: {detail or '<empty>'}"
        ) from exc


def _objects(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _plugin_record(value: Any) -> Mapping[str, Any] | None:
    for item in _objects(value):
        plugin_id = str(item.get("pluginId") or item.get("plugin_id") or item.get("id") or "")
        name = str(item.get("name") or item.get("pluginName") or "")
        marketplace = str(item.get("marketplaceName") or item.get("marketplace_name") or item.get("marketplace") or "")
        if plugin_id == PLUGIN_ID or (name == PLUGIN_NAME and marketplace == MARKETPLACE_NAME):
            return item
    return None


def _marketplace_record(value: Any) -> Mapping[str, Any] | None:
    for item in _objects(value):
        name = str(item.get("name") or item.get("marketplaceName") or item.get("marketplace_name") or "")
        if name == MARKETPLACE_NAME:
            return item
    return None


def _marketplace_matches_unityagent(record: Mapping[str, Any]) -> bool:
    serialized = json.dumps(record, ensure_ascii=False, sort_keys=True).casefold()
    return MARKETPLACE_SOURCE.casefold() in serialized and MARKETPLACE_REF.casefold() in serialized


def observe_codex_plugin(codex_path: str | None, *, runner: CommandRunner = run_command) -> dict[str, Any]:
    if not codex_path:
        return {
            "product": "unity_agent_codex_plugin",
            "status": "unavailable",
            "version": None,
            "location": None,
            "source": "requires Codex CLI",
            "sha256": None,
            "reason": "codex_cli_unavailable",
            "message": "Codex CLI is required before the UnityAgent plugin can be inspected.",
        }
    try:
        payload = _json_output(runner([codex_path, "plugin", "list", "--json"]), "codex plugin list --json")
    except CodexPluginInstallError as exc:
        return {
            "product": "unity_agent_codex_plugin",
            "status": "failed",
            "version": None,
            "location": None,
            "source": f"codex:{codex_path}",
            "sha256": None,
            "reason": str(exc),
            "message": "Codex CLI was found, but UnityAgent could not query the plugin list.",
        }

    record = _plugin_record(payload)
    if record is None:
        return {
            "product": "unity_agent_codex_plugin",
            "status": "unavailable",
            "version": None,
            "location": None,
            "source": f"github:{MARKETPLACE_SOURCE}@{MARKETPLACE_REF}",
            "sha256": None,
            "reason": "plugin_not_installed",
            "message": "Codex CLI is available, but the UnityAgent plugin is not installed yet.",
        }

    installed = record.get("installed")
    enabled = record.get("enabled")
    if installed is False or enabled is False:
        return {
            "product": "unity_agent_codex_plugin",
            "status": "unavailable",
            "version": str(record.get("version") or "") or None,
            "location": record.get("installedPath") or record.get("installed_path"),
            "source": f"codex:{PLUGIN_ID}",
            "sha256": None,
            "reason": "plugin_not_enabled",
            "message": "The UnityAgent plugin is installed but not enabled in Codex.",
        }

    version = str(record.get("version") or "") or None
    status = "verified" if version in {None, CHANNEL} else "stale"
    return {
        "product": "unity_agent_codex_plugin",
        "status": status,
        "version": version,
        "location": record.get("installedPath") or record.get("installed_path"),
        "source": f"codex:{PLUGIN_ID}",
        "sha256": None,
        "reason": None if status == "verified" else "plugin_version_mismatch",
        "message": (
            "UnityAgent Codex plugin is ready."
            if status == "verified"
            else f"UnityAgent Codex plugin version does not match {CHANNEL}."
        ),
    }


def _plugin_available(codex_path: str, runner: CommandRunner) -> bool:
    result = runner([codex_path, "plugin", "list", "--available", "--json"])
    if result.returncode != 0:
        return False
    try:
        return _plugin_record(json.loads(result.stdout)) is not None
    except json.JSONDecodeError:
        return False


def ensure_codex_plugin(codex_path: str | None, *, runner: CommandRunner = run_command) -> dict[str, Any]:
    if not codex_path:
        raise CodexPluginInstallError("Codex CLI is required before UnityAgent Plugin can be installed")

    if _plugin_available(codex_path, runner):
        marketplace_ready = True
    else:
        marketplace_payload = _json_output(
            runner([codex_path, "plugin", "marketplace", "list", "--json"]),
            "codex plugin marketplace list --json",
        )
        existing = _marketplace_record(marketplace_payload)
        if existing is not None and not _marketplace_matches_unityagent(existing):
            raise CodexPluginInstallError(
                "Codex marketplace name 'unity-agent' is already owned by another source. "
                "UnityAgent will not overwrite or retarget it automatically."
            )
        marketplace_ready = existing is not None

    if not marketplace_ready:
        _json_output(
            runner([
                codex_path,
                "plugin",
                "marketplace",
                "add",
                MARKETPLACE_SOURCE,
                "--ref",
                MARKETPLACE_REF,
                "--json",
            ]),
            "codex plugin marketplace add",
        )

    _json_output(
        runner([codex_path, "plugin", "add", PLUGIN_ID, "--json"]),
        "codex plugin add",
    )

    observation = observe_codex_plugin(codex_path, runner=runner)
    if observation["status"] != "verified":
        raise CodexPluginInstallError(
            f"Codex reported UnityAgent Plugin as {observation['status']} after installation"
        )
    return {
        "product": "unity_agent_codex_plugin",
        "status": "installed",
        "version": observation.get("version"),
        "location": observation.get("location"),
        "source": f"github:{MARKETPLACE_SOURCE}@{MARKETPLACE_REF}",
        "sha256": None,
    }
