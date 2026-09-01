"""Unity公式CLIをoptional structured Providerとして実行する。"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.Providers.UnityCli.command_builder import (
    UnityCliCommand,
    build_compile_observation_command,
    build_pipeline_catalog_command,
    build_pipeline_command,
    build_project_build_command,
    build_test_command,
)
from Runtime.Tooling.Providers.UnityCli.discovery import (
    UnityCliSurfaceDiscovery,
    discover_unity_cli_surface,
)
from Runtime.Tooling.Providers.UnityCli.result_mapper import (
    extract_command_catalog,
    normalize_build_execution,
    normalize_compile_observation,
    normalize_pipeline_command,
    normalize_test_execution,
)

SUPPORTED_CAPABILITIES = frozenset(
    {
        "project.inspect",
        "compile.observe",
        "project.test",
        "project.build",
        "scene.inspect",
    }
)
SAFE_SCENE_INSPECT_COMMANDS = frozenset(
    {
        "get_scene_hierarchy",
        "find_gameobjects",
        "editor_status",
        "get_console_logs",
    }
)
FORBIDDEN_DYNAMIC_COMMANDS = frozenset({"eval", "eval_file"})


def _failure(failure_class: str, reason: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_class": failure_class,
        "reason": reason,
        "provider_ref": "unity_cli",
        "evidence": [],
    }


class UnityCliProvider:
    """CLIの現在surfaceを再観測し、固定の安全契約内だけを実行する。"""

    def __init__(
        self,
        project_root: str | Path,
        environment_snapshot: dict[str, Any],
        *,
        dispatch_fn: Callable[..., dict[str, Any]] = dispatch,
        allowed_build_methods: set[str] | frozenset[str] | None = None,
        allowed_player_commands: set[str] | frozenset[str] | None = None,
        temp_root: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.environment_snapshot = environment_snapshot
        self.dispatch_fn = dispatch_fn
        self.allowed_build_methods = frozenset(allowed_build_methods or ())
        self.allowed_player_commands = frozenset(allowed_player_commands or ())
        if self.allowed_player_commands.intersection(FORBIDDEN_DYNAMIC_COMMANDS):
            raise ValueError("Player allowlist cannot contain eval/eval_file")
        self.temp_root = Path(temp_root or (Path(tempfile.gettempdir()) / "unityagent-unity-cli"))
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def _validate_common(
        self,
        request: dict[str, Any],
        *,
        expected_capability: str,
        policy_allowed: bool,
        approval_required: bool,
        approval_complete: bool,
    ) -> dict[str, Any] | None:
        try:
            validate_capability_request(request)
            validate_environment_snapshot(self.environment_snapshot)
        except Exception as exc:
            return _failure("precondition_failed", f"invalid runtime contract: {exc}")

        if expected_capability not in SUPPORTED_CAPABILITIES or request.get("capability") != expected_capability:
            return _failure("unsupported", f"Unity CLI Provider does not execute {request.get('capability')!r}")
        if not same_project_root(str(request.get("project_root") or ""), str(self.project_root)):
            return _failure("scope_violation", "CapabilityRequest project_root does not match Unity CLI Provider")
        snapshot_root = str((self.environment_snapshot.get("project") or {}).get("root") or "")
        if not snapshot_root or not same_project_root(snapshot_root, str(self.project_root)):
            return _failure("scope_violation", "Environment Snapshot is bound to a different project")
        if not policy_allowed:
            return _failure("blocked_by_policy", "Policy denied Unity CLI execution")
        if approval_required and (not request.get("approval_ref") or not approval_complete):
            return _failure("blocked_by_approval", "Required approval is not complete")
        if (self.environment_snapshot.get("unity_cli") or {}).get("available") is not True:
            return _failure("unavailable", "Unity CLI is not available")
        return None

    def _safe_mode_failure(self) -> dict[str, Any] | None:
        editor = self.environment_snapshot.get("unity_editor") or {}
        if editor.get("safe_mode") is True:
            return _failure("precondition_failed", "Unity CLI execution is blocked while the project is in Safe Mode")
        if editor.get("running") is True and editor.get("safe_mode") == "unknown":
            return _failure("not_observed", "running Editor Safe Mode state is unknown")
        return None

    def discover(self) -> UnityCliSurfaceDiscovery:
        return discover_unity_cli_surface(
            self.project_root,
            self.environment_snapshot,
            dispatch_fn=self.dispatch_fn,
        )

    def available_capabilities(self) -> frozenset[str]:
        discovery = self.discover()
        if discovery.status != "available":
            return frozenset()
        result: set[str] = set()
        if discovery.project_info is not None:
            result.add("project.inspect")
        if "run" in discovery.supported_commands:
            result.add("compile.observe")
        if "test" in discovery.supported_commands and (self.environment_snapshot.get("test_framework") or {}).get("available") is True:
            result.add("project.test")
        if (
            "build" in discovery.supported_commands
            and (self.environment_snapshot.get("build") or {}).get("requested_target_module_available") is True
            and bool(self.allowed_build_methods)
        ):
            result.add("project.build")
        catalog_names = {
            str(item.get("name"))
            for item in discovery.command_catalog
            if not item.get("runtime_only")
        }
        if discovery.pipeline_reachable is True and catalog_names.intersection(SAFE_SCENE_INSPECT_COMMANDS):
            result.add("scene.inspect")
        return frozenset(result)

    def _dispatch(
        self,
        command: UnityCliCommand,
        *,
        timeout_seconds: float,
        cancel_event: threading.Event | None,
    ) -> tuple[int | None, str, dict[str, Any] | None]:
        try:
            outcome = self.dispatch_fn(
                DispatchRequest(
                    command=list(command.argv),
                    cwd=self.project_root,
                    timeout_seconds=timeout_seconds,
                ),
                cancel_event=cancel_event,
            )
        except PermissionError:
            return None, "", _failure("unavailable", "Unity CLI executable is not permitted to run")
        except OSError as exc:
            return None, "", _failure("unhealthy", f"Unity CLI process could not start: {exc}")

        if outcome.get("status") == "cancelled" or outcome.get("failure_class") == "runtime_cancelled":
            return None, "", _failure("cancelled", "Unity CLI execution was cancelled")
        if outcome.get("failure_class") == "runtime_timeout":
            return None, "", _failure("timeout", "Unity CLI execution timed out")
        result = outcome.get("result")
        if result is None or getattr(result, "returncode", None) is None:
            return None, "", _failure("execution_failed", "Unity CLI process result is unavailable")
        return int(result.returncode), str(getattr(result, "stdout", "") or ""), None

    def _require_discovery(self, command_name: str) -> tuple[UnityCliSurfaceDiscovery | None, dict[str, Any] | None]:
        discovery = self.discover()
        if discovery.status != "available":
            return None, _failure(discovery.failure_class or "unavailable", discovery.reason or "Unity CLI unavailable")
        if command_name not in discovery.supported_commands:
            return None, _failure(
                "unsupported",
                f"Unity CLI command {command_name!r} is not present in the observed CLI surface",
            )
        return discovery, None

    def run_project_inspect(
        self,
        request: dict[str, Any],
        *,
        policy_allowed: bool,
    ) -> dict[str, Any]:
        failure = self._validate_common(
            request,
            expected_capability="project.inspect",
            policy_allowed=policy_allowed,
            approval_required=False,
            approval_complete=False,
        )
        if failure:
            return failure
        discovery, failure = self._require_discovery("projects")
        if failure:
            return failure
        if discovery is None or discovery.project_info is None:
            return _failure("not_observed", "structured Unity CLI project info was not observed")
        return {
            "status": "passed",
            "failure_class": None,
            "reason": None,
            "provider_ref": "unity_cli",
            "project": discovery.project_info,
            "evidence": ["project_fact"],
        }

    def run_compile(
        self,
        request: dict[str, Any],
        *,
        timeout_seconds: float,
        policy_allowed: bool,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        failure = self._validate_common(
            request,
            expected_capability="compile.observe",
            policy_allowed=policy_allowed,
            approval_required=False,
            approval_complete=False,
        )
        if failure:
            return failure
        _, failure = self._require_discovery("run")
        if failure:
            return failure
        cli = self.environment_snapshot.get("unity_cli") or {}
        command = build_compile_observation_command(
            str(cli["executable_path"]),
            self.project_root,
            timeout_seconds=timeout_seconds,
        )
        exit_code, stdout, failure = self._dispatch(
            command,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure
        normalized = normalize_compile_observation(exit_code=int(exit_code), stdout=stdout)
        return {**normalized, "provider_ref": "unity_cli"}

    def run_tests(
        self,
        request: dict[str, Any],
        *,
        run_id: str,
        timeout_seconds: float,
        policy_allowed: bool,
        test_mode: str = "EditMode",
        test_filter: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        failure = self._validate_common(
            request,
            expected_capability="project.test",
            policy_allowed=policy_allowed,
            approval_required=False,
            approval_complete=False,
        )
        if failure:
            return failure
        if (self.environment_snapshot.get("test_framework") or {}).get("available") is not True:
            return _failure("unsupported", "Unity Test Framework availability is not proven")
        failure = self._safe_mode_failure()
        if failure:
            return failure
        _, failure = self._require_discovery("test")
        if failure:
            return failure

        run_dir = (self.temp_root / run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        results_path = run_dir / "test-results.xml"
        cli = self.environment_snapshot.get("unity_cli") or {}
        command = build_test_command(
            str(cli["executable_path"]),
            self.project_root,
            output_path=results_path,
            timeout_seconds=timeout_seconds,
            test_mode=test_mode,
            test_filter=test_filter,
        )
        exit_code, stdout, failure = self._dispatch(
            command,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure
        normalized = normalize_test_execution(
            exit_code=int(exit_code),
            stdout=stdout,
            test_results_path=results_path,
        )
        return {
            **normalized,
            "provider_ref": "unity_cli",
            "test_results_path": str(results_path),
        }

    def run_build(
        self,
        request: dict[str, Any],
        *,
        timeout_seconds: float,
        policy_allowed: bool,
        execute_method: str,
        build_output_relative_path: str,
        approval_required: bool = False,
        approval_complete: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        failure = self._validate_common(
            request,
            expected_capability="project.build",
            policy_allowed=policy_allowed,
            approval_required=approval_required,
            approval_complete=approval_complete,
        )
        if failure:
            return failure
        failure = self._safe_mode_failure()
        if failure:
            return failure
        build = self.environment_snapshot.get("build") or {}
        if build.get("requested_target_module_available") is not True:
            return _failure("unsupported", "requested Unity Build Module availability is not proven")
        build_target = build.get("requested_target")
        if not isinstance(build_target, str) or not build_target:
            return _failure("precondition_failed", "requested build target is missing")
        if execute_method not in self.allowed_build_methods:
            return _failure("unsupported", f"build execute method is not repository-allowlisted: {execute_method}")
        _, failure = self._require_discovery("build")
        if failure:
            return failure

        relative_output = Path(build_output_relative_path)
        if relative_output.is_absolute() or ".." in relative_output.parts:
            return _failure("scope_violation", "build output must remain project-relative")
        build_output = (self.project_root / relative_output).resolve(strict=False)
        try:
            build_output.relative_to(self.project_root)
        except ValueError:
            return _failure("scope_violation", "build output escapes Project Root")

        cli = self.environment_snapshot.get("unity_cli") or {}
        command = build_project_build_command(
            str(cli["executable_path"]),
            self.project_root,
            build_target=build_target,
            execute_method=execute_method,
            output_path=build_output,
        )
        exit_code, stdout, failure = self._dispatch(
            command,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure
        normalized = normalize_build_execution(
            exit_code=int(exit_code),
            stdout=stdout,
            build_output_path=build_output,
        )
        return {**normalized, "provider_ref": "unity_cli"}

    def run_scene_inspect(
        self,
        request: dict[str, Any],
        *,
        command_name: str,
        command_args: list[str] | tuple[str, ...] = (),
        timeout_seconds: float,
        policy_allowed: bool,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        failure = self._validate_common(
            request,
            expected_capability="scene.inspect",
            policy_allowed=policy_allowed,
            approval_required=False,
            approval_complete=False,
        )
        if failure:
            return failure
        if command_name in FORBIDDEN_DYNAMIC_COMMANDS or command_name not in SAFE_SCENE_INSPECT_COMMANDS:
            return _failure("blocked_by_policy", f"Unity CLI scene command is not read-only allowlisted: {command_name}")
        discovery, failure = self._require_discovery("command")
        if failure:
            return failure
        if discovery is None or discovery.pipeline_reachable is not True:
            return _failure("unavailable", "Unity Pipeline is not observed reachable for this project")
        catalog = {
            str(item.get("name")): item
            for item in discovery.command_catalog
            if isinstance(item, dict)
        }
        item = catalog.get(command_name)
        if item is None or item.get("runtime_only") is True:
            return _failure("unsupported", f"allowlisted command is not exposed by the bound Editor: {command_name}")

        cli = self.environment_snapshot.get("unity_cli") or {}
        command = build_pipeline_command(
            str(cli["executable_path"]),
            self.project_root,
            command_name,
            command_args,
        )
        exit_code, stdout, failure = self._dispatch(
            command,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure
        normalized = normalize_pipeline_command(
            exit_code=int(exit_code),
            stdout=stdout,
            evidence=["editor_observation"],
        )
        return {**normalized, "provider_ref": "unity_cli", "command_name": command_name}

    def discover_player_transport(
        self,
        *,
        runtime_name: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        """Order 08がPlayer Evidenceへ昇格する前のtransport discoveryだけを返す。"""
        discovery = self.discover()
        if discovery.status != "available" or discovery.pipeline_reachable is not True:
            return _failure("unavailable", "Unity CLI/Pipeline transport is unavailable")
        cli = self.environment_snapshot.get("unity_cli") or {}
        command = build_pipeline_catalog_command(
            str(cli["executable_path"]),
            self.project_root,
            runtime_name=runtime_name,
        )
        exit_code, stdout, failure = self._dispatch(
            command,
            timeout_seconds=timeout_seconds,
            cancel_event=None,
        )
        if failure:
            return failure
        if int(exit_code) != 0:
            return _failure("unavailable", "Player Runtime command catalog is not reachable")
        try:
            catalog = extract_command_catalog(stdout)
        except ValueError as exc:
            return _failure("execution_failed", str(exc))
        runtime_only = [
            item
            for item in catalog
            if item.get("runtime_only") is True and str(item.get("name")) in self.allowed_player_commands
        ]
        return {
            "status": "passed",
            "failure_class": None,
            "reason": None,
            "provider_ref": "unity_cli",
            "runtime_name": runtime_name,
            "commands": runtime_only,
            # transport factでありPlayer Evidenceではない。
            "evidence": [],
        }
