"""UnityArtistCLI Provider adapter over the canonical Runtime dispatcher.

This adapter owns transport and structured-result normalization only. UnityAgent
continues to own Policy, approval, semantic intent, fallback, and Evidence.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.Providers.UnityArtistCli.command_builder import (
    OPTIONAL_ARGUMENTS,
    build_artist_command,
)
from Runtime.Tooling.Providers.UnityArtistCli.result_mapper import normalize_artist_result

ARTIST_PROVIDER = "unity_artist_cli"
SUPPORTED_CAPABILITIES = frozenset({"domain.workflow", "visual.capture"})
WORKFLOW_COMMANDS = {
    "capture": "capture",
    "evaluate": "evaluate",
    "refine": "refine",
    "timeline": "cinematic",
    "cinematic": "cinematic",
    "lookdev_refine": "refine",
}
DEFAULT_COMMAND = "plan"


def _failure(failure_class: str, reason: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_class": failure_class,
        "reason": reason,
        "provider_ref": ARTIST_PROVIDER,
        "evidence": [],
    }


class UnityArtistCliProvider:
    """Bounded CLI adapter selected by the existing Capability Resolver."""

    def __init__(
        self,
        project_root: str | Path,
        environment_snapshot: Mapping[str, Any],
        *,
        dispatch_fn: Callable[..., dict[str, Any]] = dispatch,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.environment_snapshot = dict(environment_snapshot)
        self.dispatch_fn = dispatch_fn

    def available_capabilities(self) -> frozenset[str]:
        facts = self.environment_snapshot.get(ARTIST_PROVIDER)
        if not isinstance(facts, Mapping):
            return frozenset()
        if all(facts.get(key) is True for key in ("available", "project_bound", "package_installed", "pipeline_reachable")):
            return SUPPORTED_CAPABILITIES
        return frozenset()

    def _validate_common(self, request: Mapping[str, Any], *, policy_allowed: bool) -> dict[str, Any] | None:
        try:
            validate_capability_request(dict(request))
            validate_environment_snapshot(dict(self.environment_snapshot))
        except Exception as exc:  # contract failures are typed preconditions
            return _failure("precondition_failed", f"invalid Runtime contract: {exc}")
        capability = str(request.get("capability") or "")
        if capability not in SUPPORTED_CAPABILITIES:
            return _failure("unsupported", f"UnityArtistCLI does not execute {capability!r}")
        if not same_project_root(str(request.get("project_root") or ""), str(self.project_root)):
            return _failure("scope_violation", "CapabilityRequest project_root does not match UnityArtistCLI Provider")
        snapshot_project = self.environment_snapshot.get("project")
        snapshot_root = snapshot_project.get("root") if isinstance(snapshot_project, Mapping) else None
        if not snapshot_root or not same_project_root(str(snapshot_root), str(self.project_root)):
            return _failure("scope_violation", "Environment Snapshot is bound to a different project")
        if not policy_allowed:
            return _failure("blocked_by_policy", "Policy denied UnityArtistCLI execution")

        facts = self.environment_snapshot.get(ARTIST_PROVIDER)
        if not isinstance(facts, Mapping):
            return _failure("unavailable", "Environment Snapshot does not contain UnityArtistCLI facts")
        required = ("available", "project_bound", "package_installed", "pipeline_reachable")
        if any(facts.get(key) is not True for key in required):
            return _failure("unavailable", "Environment Snapshot does not prove UnityArtistCLI/Pipeline project binding")
        if not facts.get("executable_path"):
            return _failure("unavailable", "UnityArtistCLI executable path was not observed")
        return None

    @staticmethod
    def _command_and_options(
        request: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> tuple[str, dict[str, object]]:
        qualifiers = request.get("qualifiers")
        qualifiers = qualifiers if isinstance(qualifiers, Mapping) else {}
        workflow = str(arguments.get("workflow") or qualifiers.get("workflow") or "")
        command = str(arguments.get("command") or "").casefold()
        if not command:
            command = WORKFLOW_COMMANDS.get(workflow, "")
        if not command:
            command = "capture" if request.get("capability") == "visual.capture" else DEFAULT_COMMAND

        options: dict[str, object] = {}
        raw_options = arguments.get("cli_options")
        if raw_options is not None:
            if not isinstance(raw_options, Mapping):
                raise ValueError("cli_options must be a mapping")
            for key, value in raw_options.items():
                option = str(key)
                if option not in OPTIONAL_ARGUMENTS:
                    raise ValueError(f"UnityArtistCLI option is not allowlisted: {option!r}")
                options[option] = value
        if workflow and "--workflow" not in options:
            options["--workflow"] = workflow
        if arguments.get("operation") is not None:
            options["--operation"] = arguments["operation"]
        if arguments.get("approval_token") is not None:
            options["--approval-token"] = arguments["approval_token"]
        if arguments.get("expected_revision") is not None:
            options["--expected-revision"] = arguments["expected_revision"]
        return command, options

    def execute(
        self,
        request: dict[str, Any],
        context: Any = None,
        arguments: Mapping[str, Any] | None = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Execute one allowlisted Artist command with explicit project binding."""
        del context  # Policy and resolution have already run in the Runtime chain.
        failure = self._validate_common(request, policy_allowed=True)
        if failure:
            return failure
        arguments = arguments or {}
        try:
            command, options = self._command_and_options(request, arguments)
            facts = self.environment_snapshot[ARTIST_PROVIDER]
            executable = str(facts["executable_path"])
            timeout_seconds = float(arguments.get("timeout_seconds", 60.0))
            dispatch_request = build_artist_command(
                executable,
                self.project_root,
                command,
                options,
                timeout_seconds=timeout_seconds,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return _failure("precondition_failed", str(exc))

        if cancel_event is not None and cancel_event.is_set():
            return _failure("cancelled", "UnityArtistCLI execution was cancelled before dispatch")
        try:
            outcome = self.dispatch_fn(dispatch_request, cancel_event=cancel_event)
        except TimeoutError:
            return _failure("timeout", "UnityArtistCLI execution timed out")
        except PermissionError:
            return _failure("unavailable", "UnityArtistCLI executable is not permitted to run")
        except (ConnectionError, OSError) as exc:
            return _failure("unhealthy", f"UnityArtistCLI transport failed: {exc}")
        if outcome.get("status") == "cancelled" or outcome.get("failure_class") == "runtime_cancelled":
            return _failure("cancelled", "UnityArtistCLI execution was cancelled")
        if outcome.get("failure_class") == "runtime_timeout":
            return _failure("timeout", "UnityArtistCLI execution timed out")
        if outcome.get("status") != "passed":
            return _failure(
                "unhealthy" if outcome.get("failure_class") == "runtime_protocol_failure" else "execution_failed",
                str(outcome.get("reason") or "UnityArtistCLI process failed"),
            )

        payload = outcome.get("payload")
        if payload is None:
            result = outcome.get("result")
            stdout = str(getattr(result, "stdout", "") or "")
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                return _failure("not_observed", "UnityArtistCLI returned non-JSON output")
        return normalize_artist_result(payload, command=command)

    def run(
        self,
        request: dict[str, Any],
        *,
        policy_allowed: bool = True,
        arguments: Mapping[str, Any] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        if not policy_allowed:
            return _failure("blocked_by_policy", "Policy denied UnityArtistCLI execution")
        return self.execute(request, arguments=arguments, cancel_event=cancel_event)
