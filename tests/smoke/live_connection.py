#!/usr/bin/env python3
"""Optional REAL Unity CLI connection/read smoke. Never reports unobserved as PASS."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from unityagent.runtime.tooling.environment.project_identity import (
    resolve_project_root,
    same_project_root,
)
from unityagent.runtime.tooling.providers.unity_cli.command_builder import (
    build_project_info_command,
    build_status_command,
    build_pipeline_catalog_command,
    build_pipeline_command,
    build_version_command,
)
from unityagent.runtime.tooling.providers.unity_cli.result_mapper import (
    normalize_project_info,
    parse_json_sequence,
    terminal_envelope,
)


class LiveSmokeFailure(RuntimeError):
    pass


class LiveSmokeUnavailable(RuntimeError):
    pass


def observe(command, project: str):
    try:
        result = subprocess.run(
            list(command.argv), cwd=project,
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
        raise LiveSmokeUnavailable(type(exc).__name__) from exc
    if result.returncode != 0:
        raise LiveSmokeUnavailable(
            f"{command.operation}: Unity CLI unavailable or refused (exit {result.returncode})"
        )
    try:
        envelope = terminal_envelope(parse_json_sequence(result.stdout, strict=True))
    except ValueError as exc:
        raise LiveSmokeFailure(f"{command.operation}: malformed structured response") from exc
    if not envelope or envelope.get("success") is not True:
        raise LiveSmokeFailure(f"{command.operation}: no successful structured observation")
    return envelope


def verify_connection(executable: str, project: str) -> dict:
    version = observe(build_version_command(executable), project)
    self_version = version.get("data")
    if not self_version:
        raise LiveSmokeFailure("Unity CLI version not observed")
    info_command = build_project_info_command(executable, project)
    project_info = observe(info_command, project)
    normalized = normalize_project_info(exit_code=0, stdout=json.dumps(project_info))
    data = normalized.get("project")
    if normalized.get("status") != "passed" or not isinstance(data, dict):
        raise LiveSmokeFailure("Project info was not observed")
    observed_root = data.get("path") or data.get("projectPath") or data.get("project_root")
    if not observed_root or not same_project_root(observed_root, project):
        raise LiveSmokeFailure("Unity CLI observed a different project")

    status = observe(build_status_command(executable, project), project)
    sessions = status.get("data")
    if isinstance(sessions, dict):
        sessions = sessions.get("instances")
    if not isinstance(sessions, list):
        raise LiveSmokeFailure("Editor status did not report instances")
    matches = [
        row for row in sessions if isinstance(row, dict)
        and any(
            value and same_project_root(value, project)
            for value in (row.get("projectPath"), row.get("project"), row.get("project_root"))
        )
        and row.get("state") in {"ready", "running"}
    ]
    if len(matches) != 1:
        raise LiveSmokeUnavailable("No unique ready Editor bound to the requested project")

    catalog = observe(build_pipeline_catalog_command(executable, project), project)
    commands = catalog.get("data")
    if isinstance(commands, dict):
        commands = commands.get("commands")
    if not isinstance(commands, list):
        raise LiveSmokeFailure("Editor command catalog not observed")
    matches = [
        row for row in commands if isinstance(row, dict)
        and row.get("name") == "get_scene_hierarchy"
        and row.get("runtimeOnly") is not True
    ]
    if len(matches) != 1:
        raise LiveSmokeUnavailable("Read-only hierarchy command not available")
    hierarchy = observe(
        build_pipeline_command(executable, project, "get_scene_hierarchy"), project
    )
    if not isinstance(hierarchy.get("data"), (dict, list)):
        raise LiveSmokeFailure("Scene hierarchy not structurally observed")
    return {
        "status": "passed",
        "observation_state": "observed",
        "checks": ["unity_cli_version", "project_binding", "editor_binding", "scene_hierarchy_read"],
        "real_editor": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Real, read-only UnityAgent connection smoke")
    parser.add_argument("--project", required=True)
    parser.add_argument("--cli", default="unity")
    arguments = parser.parse_args()
    try:
        project = resolve_project_root(arguments.project)
        executable = shutil.which(arguments.cli)
        if not executable:
            raise LiveSmokeUnavailable("Unity CLI executable not found")
        result = verify_connection(executable, project)
        exit_code = 0
    except (LiveSmokeUnavailable, ValueError) as exc:
        result = {"status": "BLOCKED_NOT_RUN", "observation_state": "not_observed", "reason": str(exc)}
        exit_code = 2
    except LiveSmokeFailure as exc:
        result = {"status": "failed", "observation_state": "failed", "reason": str(exc)}
        exit_code = 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
