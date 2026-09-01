"""Unity CLI を shell 文字列へ落とさず typed argv として構築する。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

MACHINE_FLAGS = ("--format", "json", "--non-interactive", "--no-banner")
MACHINE_NDJSON_FLAGS = ("--format", "ndjson", "--non-interactive", "--no-banner")
FORBIDDEN_COMMAND_NAMES = frozenset({"eval", "eval_file"})
SECRET_BEARING_FLAGS = frozenset(
    {
        "--client-secret",
        "--secret",
        "--serial",
        "--git-token",
        "--android-keystore-base64",
        "--android-keystore-password",
        "--android-key-alias-password",
    }
)
_METHOD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")


@dataclass(frozen=True)
class UnityCliCommand:
    argv: tuple[str, ...]
    output_format: str
    operation: str


def _non_empty(value: str | Path, *, label: str) -> str:
    text = str(value)
    if not text.strip():
        raise ValueError(f"{label} must not be empty")
    return text


def _reject_secret_flags(argv: Sequence[str]) -> None:
    lowered = [item.casefold() for item in argv]
    for index, token in enumerate(lowered):
        flag = token.split("=", 1)[0]
        if flag in SECRET_BEARING_FLAGS:
            raise ValueError(f"secret-bearing Unity CLI flag is prohibited: {argv[index]}")


def _reject_eval(command_name: str) -> None:
    if command_name.casefold() in FORBIDDEN_COMMAND_NAMES:
        raise ValueError(f"raw mutation/eval command is prohibited: {command_name}")


def validate_safe_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise ValueError("Unity CLI argv must be a non-empty string sequence")
    _reject_secret_flags(argv)
    return tuple(argv)


def _machine(argv: Iterable[str], *, ndjson: bool = False, operation: str) -> UnityCliCommand:
    flags = MACHINE_NDJSON_FLAGS if ndjson else MACHINE_FLAGS
    values = [*argv, *flags]
    return UnityCliCommand(validate_safe_argv(values), "ndjson" if ndjson else "json", operation)


def build_help_probe(executable: str | Path, command_name: str) -> UnityCliCommand:
    _reject_eval(command_name)
    return UnityCliCommand(
        validate_safe_argv(
            [
                _non_empty(executable, label="executable"),
                "--non-interactive",
                "--no-banner",
                command_name,
                "--help",
            ]
        ),
        "human",
        f"help:{command_name}",
    )


def build_project_info_command(executable: str | Path, project_root: str | Path) -> UnityCliCommand:
    return _machine(
        [
            _non_empty(executable, label="executable"),
            "projects",
            "info",
            _non_empty(project_root, label="project_root"),
        ],
        operation="project.inspect",
    )


def build_status_command(executable: str | Path) -> UnityCliCommand:
    return _machine([_non_empty(executable, label="executable"), "status"], operation="editor.status")


def build_pipeline_list_command(executable: str | Path) -> UnityCliCommand:
    return _machine([_non_empty(executable, label="executable"), "pipeline", "list"], operation="pipeline.list")


def build_pipeline_catalog_command(
    executable: str | Path,
    project_root: str | Path,
    *,
    runtime_name: str | None = None,
) -> UnityCliCommand:
    argv = [_non_empty(executable, label="executable"), "command"]
    if runtime_name is not None:
        argv.extend(["--runtime", _non_empty(runtime_name, label="runtime_name")])
    else:
        argv.extend(["--project-path", _non_empty(project_root, label="project_root")])
    return _machine(argv, operation="pipeline.catalog")


def build_pipeline_command(
    executable: str | Path,
    project_root: str | Path,
    command_name: str,
    command_args: Sequence[str] = (),
    *,
    runtime_name: str | None = None,
) -> UnityCliCommand:
    _reject_eval(command_name)
    argv = [_non_empty(executable, label="executable"), "command", command_name]
    if runtime_name is not None:
        argv.extend(["--runtime", _non_empty(runtime_name, label="runtime_name")])
    else:
        argv.extend(["--project-path", _non_empty(project_root, label="project_root")])
    argv.extend(command_args)
    return _machine(argv, operation=f"pipeline.command:{command_name}")


def build_compile_observation_command(
    executable: str | Path,
    project_root: str | Path,
    *,
    timeout_seconds: float,
) -> UnityCliCommand:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    # bare `unity run` は batch Editor を一度だけ起動し、Project load/compile の成否を返す。
    return _machine(
        [
            _non_empty(executable, label="executable"),
            "run",
            _non_empty(project_root, label="project_root"),
            "--timeout",
            str(int(timeout_seconds)),
        ],
        ndjson=True,
        operation="compile.observe",
    )


def build_test_command(
    executable: str | Path,
    project_root: str | Path,
    *,
    output_path: str | Path,
    timeout_seconds: float,
    test_mode: str = "EditMode",
    test_filter: str | None = None,
) -> UnityCliCommand:
    if test_mode not in {"EditMode", "PlayMode"}:
        raise ValueError("test_mode must be EditMode or PlayMode")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    argv = [
        _non_empty(executable, label="executable"),
        "test",
        _non_empty(project_root, label="project_root"),
        "--mode",
        test_mode,
        "--output",
        _non_empty(output_path, label="output_path"),
        "--timeout",
        str(int(timeout_seconds)),
    ]
    if test_filter is not None:
        argv.extend(["--filter", _non_empty(test_filter, label="test_filter")])
    # --allow-install は追加しない。Provider 不足を理由に環境を変更しない。
    return _machine(argv, operation="project.test")


def build_project_build_command(
    executable: str | Path,
    project_root: str | Path,
    *,
    build_target: str,
    execute_method: str,
    output_path: str | Path,
) -> UnityCliCommand:
    if not _METHOD_RE.fullmatch(execute_method):
        raise ValueError("execute_method must be an existing fully-qualified static method name")
    argv = [
        _non_empty(executable, label="executable"),
        "build",
        _non_empty(project_root, label="project_root"),
        "--target",
        _non_empty(build_target, label="build_target"),
        "--execute-method",
        execute_method,
        "--output-path",
        _non_empty(output_path, label="output_path"),
    ]
    # CLI install/update/signing secret convenience flagsはProviderから公開しない。
    return _machine(argv, ndjson=True, operation="project.build")


def build_shell_ndjson_command(executable: str | Path) -> UnityCliCommand:
    return UnityCliCommand(
        validate_safe_argv(
            [
                _non_empty(executable, label="executable"),
                "shell",
                "--protocol",
                "ndjson",
                "--non-interactive",
                "--no-banner",
            ]
        ),
        "ndjson",
        "shell.ndjson",
    )
