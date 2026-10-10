"""Native Unity Editor subprocess 用の typed argv builder。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
REPOSITORY_EXECUTE_METHOD_ALLOWLIST: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NativeUnityCommand:
    command: tuple[str, ...]
    log_path: Path
    test_results_path: Path | None = None
    build_output_path: Path | None = None


def validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must contain only letters, digits, '.', '_' or '-'")
    return run_id


def prepare_run_directory(temp_root: Path, run_id: str) -> Path:
    safe_run_id = validate_run_id(run_id)
    run_dir = temp_root.resolve(strict=False) / safe_run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _base_command(
    *,
    executable_path: Path,
    project_root: Path,
    log_path: Path,
    quit_after: bool,
) -> list[str]:
    # shell=False の argv を使うため、空白を含む Windows path も手動 quote しない。
    command = [
        str(executable_path),
        "-batchmode",
        "-projectPath",
        str(project_root),
        "-logFile",
        str(log_path),
    ]
    if quit_after:
        command.append("-quit")
    return command


def build_compile_command(
    *,
    executable_path: Path,
    project_root: Path,
    log_path: Path,
) -> NativeUnityCommand:
    return NativeUnityCommand(
        command=tuple(
            _base_command(
                executable_path=executable_path,
                project_root=project_root,
                log_path=log_path,
                quit_after=True,
            )
        ),
        log_path=log_path,
    )


def build_test_command(
    *,
    executable_path: Path,
    project_root: Path,
    log_path: Path,
    test_results_path: Path,
    test_platform: str = "EditMode",
) -> NativeUnityCommand:
    if not test_platform or test_platform.startswith("-"):
        raise ValueError("test_platform must be a concrete Unity Test Framework platform")
    command = _base_command(
        executable_path=executable_path,
        project_root=project_root,
        log_path=log_path,
        quit_after=False,
    )
    command.extend(
        [
            "-runTests",
            "-testPlatform",
            test_platform,
            "-testResults",
            str(test_results_path),
        ]
    )
    return NativeUnityCommand(
        command=tuple(command),
        log_path=log_path,
        test_results_path=test_results_path,
    )


def build_player_command(
    *,
    executable_path: Path,
    project_root: Path,
    log_path: Path,
    build_output_path: Path,
    build_target: str | None,
    active_build_profile: str | None = None,
) -> NativeUnityCommand:
    if not build_target and not active_build_profile:
        raise ValueError("build_target or active_build_profile is required")
    if build_target and build_target.startswith("-"):
        raise ValueError("build_target must not be another command-line option")
    if active_build_profile and active_build_profile.startswith("-"):
        raise ValueError("active_build_profile must not be another command-line option")

    command = _base_command(
        executable_path=executable_path,
        project_root=project_root,
        log_path=log_path,
        quit_after=True,
    )
    command.extend(["-build", str(build_output_path)])
    if build_target:
        command.extend(["-buildTarget", build_target])
    if active_build_profile:
        command.extend(["-activeBuildProfile", active_build_profile])
    return NativeUnityCommand(
        command=tuple(command),
        log_path=log_path,
        build_output_path=build_output_path,
    )


def build_execute_method_command(
    *,
    executable_path: Path,
    project_root: Path,
    log_path: Path,
    method_name: str,
) -> NativeUnityCommand:
    if method_name not in REPOSITORY_EXECUTE_METHOD_ALLOWLIST:
        raise ValueError(f"executeMethod is not repository-allowlisted: {method_name}")
    command = _base_command(
        executable_path=executable_path,
        project_root=project_root,
        log_path=log_path,
        quit_after=True,
    )
    command.extend(["-executeMethod", method_name])
    return NativeUnityCommand(command=tuple(command), log_path=log_path)
