"""Unity Editor 本体を bounded subprocess として実行する Provider。"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Sequence

from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot
from Runtime.Tooling.Environment.native_editor_discovery import (
    EditorCandidate,
    EditorProcessObservation,
    bind_editor_processes,
    discover_editor_processes,
    enumerate_native_editor_candidates,
)
from Runtime.Tooling.Environment.project_identity import read_project_version, same_project_root
from Runtime.Tooling.Providers.NativeUnityEditor.log_parser import (
    normalize_build_result,
    normalize_compile_result,
    normalize_test_result,
)
from Runtime.Tooling.Providers.NativeUnityEditor.process_builder import (
    NativeUnityCommand,
    build_compile_command,
    build_player_command,
    build_test_command,
    prepare_run_directory,
)

SUPPORTED_CAPABILITIES = frozenset({"compile.observe", "project.test", "project.build"})


def _failure(failure_class: str, reason: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_class": failure_class,
        "reason": reason,
        "provider_ref": "native_unity_editor",
        "evidence": [],
    }


class NativeUnityEditorProvider:
    """汎用 executeMethod を公開せず、Compile/Test/Build のみを実行する。"""

    def __init__(
        self,
        project_root: str | Path,
        environment_snapshot: dict[str, Any],
        *,
        dispatch_fn: Callable[..., dict[str, Any]] = dispatch,
        process_probe_fn: Callable[..., Sequence[EditorProcessObservation] | None] = discover_editor_processes,
        editor_candidates: Sequence[EditorCandidate] | None = None,
        temp_root: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.environment_snapshot = environment_snapshot
        self.dispatch_fn = dispatch_fn
        self.process_probe_fn = process_probe_fn
        self.editor_candidates = list(editor_candidates) if editor_candidates is not None else None
        self.temp_root = Path(temp_root or (Path(tempfile.gettempdir()) / "unityagent-native-editor"))
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
            # Runtime boundary では不正な入力を実行へ流さない。
            return _failure("precondition_failed", f"invalid runtime contract: {exc}")

        if expected_capability not in SUPPORTED_CAPABILITIES or request.get("capability") != expected_capability:
            return _failure("unsupported", f"Native Editor Provider does not execute {request.get('capability')!r}")
        if not same_project_root(str(request.get("project_root") or ""), str(self.project_root)):
            return _failure("scope_violation", "CapabilityRequest project_root does not match Native Editor Provider")
        snapshot_root = str((self.environment_snapshot.get("project") or {}).get("root") or "")
        if not snapshot_root or not same_project_root(snapshot_root, str(self.project_root)):
            return _failure("scope_violation", "Environment Snapshot is bound to a different project")
        if not policy_allowed:
            return _failure("blocked_by_policy", "Policy denied Native Editor execution")
        if approval_required and (not request.get("approval_ref") or not approval_complete):
            return _failure("blocked_by_approval", "Required approval is not complete")
        return None

    def _resolve_editor_executable(self) -> tuple[Path | None, dict[str, Any] | None]:
        project_version = read_project_version(self.project_root)
        if not project_version:
            return None, _failure("precondition_failed", "ProjectVersion.txt does not provide an Editor version")

        editor = self.environment_snapshot.get("unity_editor") or {}
        snapshot_path = editor.get("executable_path")
        if editor.get("installed") is True and editor.get("project_version_match") is True and snapshot_path:
            candidate = Path(str(snapshot_path)).expanduser().resolve(strict=False)
            if candidate.is_file():
                return candidate, None

        candidates = self.editor_candidates
        if candidates is None:
            candidates = enumerate_native_editor_candidates(project_version=project_version)
        exact = [
            Path(item.executable_path).expanduser().resolve(strict=False)
            for item in candidates
            if item.version == project_version and Path(item.executable_path).is_file()
        ]
        unique = sorted({str(path): path for path in exact}.values(), key=lambda path: str(path))
        if not unique:
            return None, _failure("unavailable", f"matching Unity Editor executable is unavailable: {project_version}")
        if len(unique) > 1:
            return None, _failure("ambiguous_binding", f"multiple matching Unity Editor executables observed: {project_version}")
        return unique[0], None

    def _check_editor_conflict(self) -> dict[str, Any] | None:
        try:
            processes = self.process_probe_fn(cwd=self.project_root)
        except Exception as exc:
            return _failure("not_observed", f"unable to observe Unity Editor process state: {exc}")

        if processes is not None:
            binding = bind_editor_processes(str(self.project_root), processes)
            if binding["binding_status"] == "ambiguous_binding":
                return _failure("ambiguous_binding", "multiple Unity Editor instances are bound to this project")
            if binding["binding_status"] == "bound":
                return _failure("precondition_failed", "an existing Unity Editor instance already has this project open")
            return None

        editor = self.environment_snapshot.get("unity_editor") or {}
        binding_status = editor.get("binding_status")
        if binding_status == "ambiguous_binding":
            return _failure("ambiguous_binding", "Environment Snapshot has ambiguous Editor binding")
        if binding_status == "bound":
            return _failure("precondition_failed", "Environment Snapshot reports this project open in another Editor")
        if editor.get("running") == "unknown":
            return _failure("not_observed", "Editor process state is unknown; second-Editor safety cannot be proven")
        return None

    def _safe_mode_failure(self) -> dict[str, Any] | None:
        safe_mode = (self.environment_snapshot.get("unity_editor") or {}).get("safe_mode")
        if safe_mode is True:
            return _failure("precondition_failed", "Native Editor execution is blocked while the project is in Safe Mode")
        if safe_mode == "unknown":
            return _failure("not_observed", "Safe Mode state is unknown")
        return None

    def _prepare_command(self, run_id: str, kind: str) -> tuple[Path, Path]:
        run_dir = prepare_run_directory(self.temp_root, run_id)
        return run_dir, run_dir / f"{kind}.log"

    def _dispatch_command(
        self,
        command: NativeUnityCommand,
        *,
        timeout_seconds: float,
        cancel_event: threading.Event | None,
    ) -> tuple[int | None, str, dict[str, Any] | None]:
        outcome = self.dispatch_fn(
            DispatchRequest(
                command=list(command.command),
                cwd=self.project_root,
                timeout_seconds=timeout_seconds,
            ),
            cancel_event=cancel_event,
        )
        result = outcome.get("result")
        log_text = ""
        try:
            if command.log_path.is_file():
                log_text = command.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log_text = ""

        if outcome.get("status") == "cancelled" or outcome.get("failure_class") == "runtime_cancelled":
            return None, log_text, _failure("cancelled", "Native Unity Editor execution was cancelled")
        if outcome.get("failure_class") == "runtime_timeout":
            return None, log_text, _failure("timeout", "Native Unity Editor execution timed out")
        if result is None or getattr(result, "returncode", None) is None:
            return None, log_text, _failure("execution_failed", "subprocess result is unavailable")
        return int(result.returncode), log_text, None

    def run_compile(
        self,
        request: dict[str, Any],
        *,
        run_id: str,
        timeout_seconds: float,
        policy_allowed: bool,
        approval_required: bool = False,
        approval_complete: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        failure = self._validate_common(
            request,
            expected_capability="compile.observe",
            policy_allowed=policy_allowed,
            approval_required=approval_required,
            approval_complete=approval_complete,
        )
        if failure:
            return failure
        conflict = self._check_editor_conflict()
        if conflict:
            return conflict
        executable, failure = self._resolve_editor_executable()
        if failure:
            return failure
        _, log_path = self._prepare_command(run_id, "compile")
        command = build_compile_command(
            executable_path=executable,
            project_root=self.project_root,
            log_path=log_path,
        )
        exit_code, log_text, failure = self._dispatch_command(
            command,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure
        normalized = normalize_compile_result(exit_code=int(exit_code), log_text=log_text)
        return {**normalized, "provider_ref": "native_unity_editor", "log_path": str(log_path)}

    def run_tests(
        self,
        request: dict[str, Any],
        *,
        run_id: str,
        timeout_seconds: float,
        policy_allowed: bool,
        test_platform: str = "EditMode",
        approval_required: bool = False,
        approval_complete: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        failure = self._validate_common(
            request,
            expected_capability="project.test",
            policy_allowed=policy_allowed,
            approval_required=approval_required,
            approval_complete=approval_complete,
        )
        if failure:
            return failure
        if (self.environment_snapshot.get("test_framework") or {}).get("available") is not True:
            return _failure("unsupported", "Unity Test Framework availability is not proven")
        failure = self._safe_mode_failure() or self._check_editor_conflict()
        if failure:
            return failure
        executable, failure = self._resolve_editor_executable()
        if failure:
            return failure

        run_dir, log_path = self._prepare_command(run_id, "tests")
        results_path = run_dir / "test-results.xml"
        command = build_test_command(
            executable_path=executable,
            project_root=self.project_root,
            log_path=log_path,
            test_results_path=results_path,
            test_platform=test_platform,
        )
        exit_code, log_text, failure = self._dispatch_command(
            command,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure
        normalized = normalize_test_result(
            exit_code=int(exit_code),
            log_text=log_text,
            test_results_path=results_path,
        )
        return {
            **normalized,
            "provider_ref": "native_unity_editor",
            "log_path": str(log_path),
            "test_results_path": str(results_path),
        }

    def run_build(
        self,
        request: dict[str, Any],
        *,
        run_id: str,
        timeout_seconds: float,
        policy_allowed: bool,
        build_output_relative_path: str,
        active_build_profile: str | None = None,
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

        build = self.environment_snapshot.get("build") or {}
        if build.get("requested_target_module_available") is not True:
            return _failure("unsupported", "requested Unity Build Module availability is not proven")
        build_target = build.get("requested_target")
        if not build_target and not active_build_profile:
            return _failure("precondition_failed", "requested build target/profile is missing")

        failure = self._safe_mode_failure() or self._check_editor_conflict()
        if failure:
            return failure
        executable, failure = self._resolve_editor_executable()
        if failure:
            return failure

        try:
            relative_output = Path(build_output_relative_path)
            if relative_output.is_absolute() or ".." in relative_output.parts:
                raise ValueError("build output must be project-relative and cannot traverse parents")
            build_output = (self.project_root / relative_output).resolve(strict=False)
            build_output.relative_to(self.project_root)
        except (ValueError, OSError) as exc:
            return _failure("scope_violation", f"unsafe build output path: {exc}")

        _, log_path = self._prepare_command(run_id, "build")
        command = build_player_command(
            executable_path=executable,
            project_root=self.project_root,
            log_path=log_path,
            build_output_path=build_output,
            build_target=str(build_target) if build_target else None,
            active_build_profile=active_build_profile,
        )
        exit_code, log_text, failure = self._dispatch_command(
            command,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure
        normalized = normalize_build_result(
            exit_code=int(exit_code),
            log_text=log_text,
            build_output_path=build_output,
        )
        return {**normalized, "provider_ref": "native_unity_editor", "log_path": str(log_path)}
