"""Bounded infrastructure recovery for Unity Safe Mode and provider disruption.

Runtime may repair infrastructure preconditions that are already explicitly
authorized (for example, applying one exact source patch and restarting the exact
Editor instance bound to the project). It never invents a patch, expands scope,
kills all Unity processes, or semantically replans the task.
"""
from __future__ import annotations

import os
import platform
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from Runtime.Guardrails.tool_runtime_guard import (
    guard_runtime_dispatch,
    mutation_scope_fingerprint,
)
from Runtime.Health.probes import rediscover_environment_snapshot
from Runtime.Tooling.Environment.native_editor_discovery import (
    EditorProcessObservation,
    discover_editor_processes,
)
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.Providers.File.file_provider import FileProvider
from Runtime.Tooling.Providers.NativeUnityEditor.log_parser import (
    CompilerDiagnostic,
    parse_compiler_diagnostics,
)
from Runtime.Tooling.capability_resolver import ResolutionContext
from Runtime.Tooling.tool_broker import ToolBroker


@dataclass(frozen=True)
class ExactSourcePatch:
    relative_path: str
    expected_text: str
    replacement_text: str


@dataclass(frozen=True)
class SafeModeRecoveryPlan:
    patch_request: dict[str, Any]
    patch: ExactSourcePatch
    scope_fingerprint: str | None

    @classmethod
    def create(
        cls,
        *,
        patch_request: dict[str, Any],
        patch: ExactSourcePatch,
    ) -> "SafeModeRecoveryPlan":
        if patch_request.get("capability") != "source.patch":
            raise ValueError("Safe Mode recovery patch must use source.patch")
        if not patch.relative_path.casefold().endswith(".cs"):
            raise ValueError("Safe Mode recovery may patch only C# source files")
        return cls(
            patch_request=dict(patch_request),
            patch=patch,
            scope_fingerprint=mutation_scope_fingerprint(patch_request),
        )


@dataclass
class SafeModeRecoveryBudget:
    maximum_cycles: int = 1
    cycles_used: int = 0

    def __post_init__(self) -> None:
        if self.maximum_cycles < 1 or self.maximum_cycles > 3:
            raise ValueError("maximum_cycles must be between 1 and 3")

    def consume(self) -> bool:
        if self.cycles_used >= self.maximum_cycles:
            return False
        self.cycles_used += 1
        return True


def _failure(failure_class: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_class": failure_class,
        "reason": reason,
        "verified": False,
        "evidence": [],
        **extra,
    }


def _pid_from_instance_id(instance_id: Any) -> int | None:
    text = str(instance_id or "")
    if not text.startswith("pid:"):
        return None
    value = text[4:]
    if not value.isdigit():
        return None
    pid = int(value)
    return pid if pid > 0 else None


def _normalize_diagnostic_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./").casefold()


def validate_narrow_compiler_diagnostics(
    *,
    diagnostics: Sequence[CompilerDiagnostic],
    patch_relative_path: str,
) -> tuple[bool, str | None]:
    """Require compiler errors to identify exactly the pre-authorized source target."""
    errors = [item for item in diagnostics if item.severity.casefold() == "error"]
    if not errors:
        return False, "no compiler error diagnostics were observed"
    target = _normalize_diagnostic_path(patch_relative_path)
    observed_targets: set[str] = set()
    for item in errors:
        if not item.path:
            return False, "compiler error path is unknown; narrow recovery target is not proven"
        observed = _normalize_diagnostic_path(item.path)
        if observed.endswith(target):
            observed_targets.add(target)
        else:
            observed_targets.add(observed)
    if observed_targets != {target}:
        return False, (
            "compiler errors span a different source target; "
            f"observed={sorted(observed_targets)} expected={target}"
        )
    return True, None


def validate_exact_editor_target(
    *,
    project_root: str | Path,
    environment_snapshot: dict[str, Any],
    processes: Sequence[EditorProcessObservation] | None,
) -> tuple[EditorProcessObservation | None, dict[str, Any] | None]:
    """Revalidate the exact bound PID/project before any termination."""
    editor = environment_snapshot.get("unity_editor") or {}
    expected_pid = _pid_from_instance_id(editor.get("bound_instance_id"))
    if expected_pid is None:
        return None, _failure(
            "not_observed",
            "Environment Snapshot does not identify the target Editor as an exact PID",
        )
    if processes is None:
        return None, _failure(
            "not_observed",
            "Unity Editor process list could not be observed before restart",
        )

    matches = [item for item in processes if item.pid == expected_pid]
    if len(matches) != 1:
        return None, _failure(
            "precondition_failed",
            f"exact target PID {expected_pid} is no longer uniquely observable",
        )
    target = matches[0]
    if not target.project_root or not same_project_root(
        target.project_root,
        str(project_root),
    ):
        return None, _failure(
            "scope_violation",
            "target PID is not bound to the requested project; refusing termination",
        )
    if target.safe_mode is not True:
        return None, _failure(
            "precondition_failed",
            "target Editor is no longer observed in Safe Mode",
        )

    expected_executable = editor.get("executable_path")
    if expected_executable and target.executable_path:
        left = str(Path(str(expected_executable)).expanduser().resolve(strict=False))
        right = str(Path(str(target.executable_path)).expanduser().resolve(strict=False))
        if os.path.normcase(left) != os.path.normcase(right):
            return None, _failure(
                "precondition_failed",
                "target PID executable no longer matches the bound Editor executable",
            )
    return target, None


def terminate_exact_editor_process(
    pid: int,
    *,
    platform_name: str | None = None,
) -> bool:
    """Terminate exactly one already-revalidated PID; never enumerate/kill Unity globally."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ValueError("pid must be a positive integer")
    system = (platform_name or platform.system()).lower()
    if system.startswith("win"):
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        return completed.returncode == 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    return True


def restart_exact_editor(
    executable_path: str | Path,
    project_root: str | Path,
) -> int:
    """Restart the exact Editor executable for the exact project without shell evaluation."""
    executable = Path(executable_path).expanduser().resolve(strict=False)
    project = Path(project_root).expanduser().resolve(strict=False)
    if not executable.is_file():
        raise FileNotFoundError(f"Unity Editor executable is unavailable: {executable}")
    if not project.is_dir():
        raise FileNotFoundError(f"Unity project is unavailable: {project}")
    process = subprocess.Popen(
        [str(executable), "-projectPath", str(project)],
        cwd=project,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
    )
    return int(process.pid)


class SafeModeRecoveryCoordinator:
    """One current-run bounded Safe Mode recovery coordinator."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        broker: ToolBroker | None = None,
        budget: SafeModeRecoveryBudget | None = None,
        process_probe_fn: Callable[..., Sequence[EditorProcessObservation] | None] = discover_editor_processes,
        terminate_fn: Callable[[int], bool] = terminate_exact_editor_process,
        restart_fn: Callable[[str | Path, str | Path], int] = restart_exact_editor,
        rediscover_fn: Callable[..., Any] = rediscover_environment_snapshot,
        file_provider_factory: Callable[[str | Path], FileProvider] = FileProvider,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.broker = broker or ToolBroker()
        self.budget = budget or SafeModeRecoveryBudget()
        self.process_probe_fn = process_probe_fn
        self.terminate_fn = terminate_fn
        self.restart_fn = restart_fn
        self.rediscover_fn = rediscover_fn
        self.file_provider_factory = file_provider_factory

    def recover(
        self,
        original_request: dict[str, Any],
        environment_snapshot: dict[str, Any],
        *,
        capability_context: ResolutionContext,
        plan: SafeModeRecoveryPlan,
        patch_context: ResolutionContext,
        compiler_log_text: str,
        rediscovery_kwargs: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.budget.consume():
            return _failure(
                "precondition_failed",
                "Safe Mode recovery cycle budget is exhausted",
                recovery_cycles_used=self.budget.cycles_used,
            )

        if not same_project_root(
            str(original_request.get("project_root") or ""),
            str(self.project_root),
        ):
            return _failure(
                "scope_violation",
                "original CapabilityRequest is bound to a different project",
            )
        snapshot_project = environment_snapshot.get("project") or {}
        if not same_project_root(
            str(snapshot_project.get("root") or ""),
            str(self.project_root),
        ):
            return _failure(
                "scope_violation",
                "Environment Snapshot is bound to a different project",
            )
        editor = environment_snapshot.get("unity_editor") or {}
        if editor.get("safe_mode") is not True:
            return _failure(
                "precondition_failed",
                "Safe Mode recovery requested while Safe Mode is not observed",
            )
        if editor.get("binding_status") != "bound" or editor.get("project_bound") is not True:
            return _failure(
                "precondition_failed",
                "Safe Mode Editor is not exactly project-bound",
            )

        if mutation_scope_fingerprint(plan.patch_request) != plan.scope_fingerprint:
            return _failure(
                "scope_violation",
                "approved recovery Mutation Scope changed after plan creation",
            )
        patch_guard = guard_runtime_dispatch(
            plan.patch_request,
            environment_snapshot,
            context=patch_context,
            original_request=plan.patch_request,
        )
        if not patch_guard.allowed:
            return _failure(
                patch_guard.failure_class or "precondition_failed",
                patch_guard.reason or "source patch dispatch guard rejected recovery",
            )

        diagnostics = parse_compiler_diagnostics(compiler_log_text)
        narrow, reason = validate_narrow_compiler_diagnostics(
            diagnostics=diagnostics,
            patch_relative_path=plan.patch.relative_path,
        )
        if not narrow:
            return _failure(
                "not_observed",
                reason or "narrow compiler recovery target is not proven",
                diagnostics=[
                    {
                        "path": item.path,
                        "line": item.line,
                        "column": item.column,
                        "severity": item.severity,
                        "code": item.code,
                        "message": item.message,
                    }
                    for item in diagnostics
                ],
            )

        try:
            processes = self.process_probe_fn(cwd=self.project_root)
        except Exception as exc:
            return _failure(
                "not_observed",
                f"failed to re-observe target Editor process: {exc}",
            )
        target_process, failure = validate_exact_editor_target(
            project_root=self.project_root,
            environment_snapshot=environment_snapshot,
            processes=processes,
        )
        if failure:
            return failure
        assert target_process is not None

        file_provider = self.file_provider_factory(self.project_root)
        patch_result = file_provider.patch_text(
            plan.patch_request,
            relative_path=plan.patch.relative_path,
            expected_text=plan.patch.expected_text,
            replacement_text=plan.patch.replacement_text,
            policy_allowed=patch_context.policy_allowed,
            approval_required=patch_context.approval_required is True,
            approval_complete=patch_context.approval_complete is True,
        )
        if patch_result.get("status") != "passed":
            return {
                **patch_result,
                "verified": False,
                "recovery_cycles_used": self.budget.cycles_used,
            }

        try:
            processes_after_patch = self.process_probe_fn(cwd=self.project_root)
        except Exception as exc:
            return _failure(
                "not_observed",
                f"failed to re-observe target Editor before termination: {exc}",
                patch_result=patch_result,
            )
        revalidated_target, failure = validate_exact_editor_target(
            project_root=self.project_root,
            environment_snapshot=environment_snapshot,
            processes=processes_after_patch,
        )
        if failure:
            return {
                **failure,
                "patch_result": patch_result,
            }
        assert revalidated_target is not None
        if revalidated_target.pid != target_process.pid:
            return _failure(
                "precondition_failed",
                "target Editor PID changed after source patch; refusing termination",
                patch_result=patch_result,
            )

        if not self.terminate_fn(revalidated_target.pid):
            return _failure(
                "execution_failed",
                f"exact target PID {revalidated_target.pid} could not be terminated",
                patch_result=patch_result,
            )

        executable = editor.get("executable_path") or revalidated_target.executable_path
        if not executable:
            return _failure(
                "not_observed",
                "exact Unity Editor executable is unknown after source patch",
                patch_result=patch_result,
            )
        try:
            restarted_pid = self.restart_fn(str(executable), self.project_root)
        except Exception as exc:
            return _failure(
                "execution_failed",
                f"exact Unity Editor restart failed: {exc}",
                patch_result=patch_result,
            )

        try:
            rediscovered = self.rediscover_fn(
                project_root=str(self.project_root),
                mutation_allowed_paths=list(
                    (plan.patch_request.get("mutation_scope") or {}).get(
                        "allowed_paths"
                    )
                    or []
                ),
                **dict(rediscovery_kwargs or {}),
            )
        except Exception as exc:
            return _failure(
                "not_observed",
                f"environment re-discovery failed after restart: {exc}",
                patch_result=patch_result,
                restarted_pid=restarted_pid,
            )
        snapshot_after = (
            rediscovered.to_dict()
            if hasattr(rediscovered, "to_dict")
            else rediscovered
        )
        if not isinstance(snapshot_after, dict):
            return _failure(
                "not_observed",
                "environment re-discovery did not return a structured snapshot",
                patch_result=patch_result,
                restarted_pid=restarted_pid,
            )

        guard = guard_runtime_dispatch(
            original_request,
            snapshot_after,
            context=capability_context,
            original_request=original_request,
        )
        if not guard.allowed:
            return _failure(
                guard.failure_class or "precondition_failed",
                guard.reason or "original capability failed post-recovery guard",
                patch_result=patch_result,
                restarted_pid=restarted_pid,
                environment_snapshot=snapshot_after,
            )

        resolution = self.broker.resolve(
            original_request,
            snapshot_after,
            context=capability_context,
        )
        if resolution.get("status") != "resolved":
            return {
                "status": "partial",
                "failure_class": resolution.get("failure_class"),
                "reason": (
                    "Safe Mode infrastructure recovery completed, but the original "
                    "capability is still not safely resolvable"
                ),
                "verified": False,
                "evidence": list(patch_result.get("evidence") or []),
                "patch_result": patch_result,
                "restarted_pid": restarted_pid,
                "environment_snapshot": snapshot_after,
                "capability_resolution": resolution,
                "recovery_cycles_used": self.budget.cycles_used,
            }

        return {
            "status": "recovered",
            "failure_class": None,
            "reason": None,
            "verified": False,
            "original_capability_status": "ready_for_retry",
            "evidence": list(patch_result.get("evidence") or []),
            "patch_result": patch_result,
            "restarted_pid": restarted_pid,
            "environment_snapshot": snapshot_after,
            "capability_resolution": resolution,
            "recovery_cycles_used": self.budget.cycles_used,
        }
