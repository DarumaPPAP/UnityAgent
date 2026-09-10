"""Typed, allowlisted UnityArtistCLI argv construction."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest

ARTIST_COMMANDS = frozenset(
    {
        "inspect",
        "plan",
        "preview",
        "apply",
        "capture",
        "evaluate",
        "refine",
        "history",
        "cinematic",
    }
)
FORBIDDEN_COMMANDS = frozenset({"eval", "eval_file", "shell", "gameobject", "hierarchy", "save"})
OPTIONAL_ARGUMENTS = frozenset(
    {
        "--request-json",
        "--intent-file",
        "--plan-id",
        "--capture-id",
        "--evaluation-id",
        "--expected-revision",
        "--approval-token",
        "--decision",
        "--notes",
        "--workflow",
        "--operation",
    }
)


def build_artist_command(
    executable: str | Path,
    project_root: str | Path,
    command_name: str,
    arguments: Mapping[str, object] | None = None,
    *,
    timeout_seconds: float = 60.0,
) -> DispatchRequest:
    """Build one machine-readable command; arbitrary CLI command names are rejected."""
    command = str(command_name).casefold()
    if command not in ARTIST_COMMANDS or command in FORBIDDEN_COMMANDS:
        raise ValueError(f"UnityArtistCLI command is not allowlisted: {command_name!r}")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    argv = [str(executable), command, "--project-path", str(project_root)]
    for option, value in (arguments or {}).items():
        if option not in OPTIONAL_ARGUMENTS:
            raise ValueError(f"UnityArtistCLI option is not allowlisted: {option!r}")
        if value is None:
            continue
        text = str(value)
        if not text:
            raise ValueError(f"UnityArtistCLI option {option!r} must not be empty")
        argv.extend([option, text])
    argv.extend(["--format", "json", "--non-interactive", "--no-banner"])
    if any(token.casefold() in FORBIDDEN_COMMANDS for token in argv):
        raise ValueError("UnityArtistCLI argv contains a forbidden command")
    return DispatchRequest(
        command=argv,
        cwd=Path(project_root).resolve(),
        timeout_seconds=float(timeout_seconds),
        expect_json=True,
    )
