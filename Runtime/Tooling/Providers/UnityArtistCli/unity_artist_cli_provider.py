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
        # Policy and resolution have already run in the Runtime chain.  Keep
        # the context binding available for the provider-owned reference
        # workflow, which delegates through the same execute method for its
        # plan/preview/apply/capture sequence.
        failure = self._validate_common(request, policy_allowed=True)
        if failure:
            return failure
        arguments = arguments or {}
        if arguments.get("reference_action") is not None:
            return self.execute_camera_fov_reference(request, context=context, arguments=arguments, cancel_event=cancel_event)
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

    @staticmethod
    def _nested_value(value: Any, names: tuple[str, ...]) -> Any:
        if isinstance(value, Mapping):
            for name in names:
                if name in value:
                    return value[name]
            for item in value.values():
                found = UnityArtistCliProvider._nested_value(item, names)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = UnityArtistCliProvider._nested_value(item, names)
                if found is not None:
                    return found
        elif isinstance(value, str) and value.lstrip().startswith(("{", "[")):
            # UnityArtistCLI's official host adapter carries the Editor
            # pipeline result as a JSON string inside provider.data.result.
            # Decode only object/array-looking values so the typed workflow
            # can inspect plan/apply/capture fields without adding a second
            # transport path.
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return None
            return UnityArtistCliProvider._nested_value(decoded, names)
        return None

    def execute_camera_fov_reference(
        self,
        request: dict[str, Any],
        *,
        context: Any = None,
        arguments: Mapping[str, Any] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Run the approved plan/preview/apply/capture sequence via this Provider."""
        del context
        arguments = arguments or {}
        reference = arguments.get("reference_action")
        if isinstance(reference, Mapping) and reference.get("contract_type") == "TypedAction":
            reference = reference.get("value")
        if not isinstance(reference, Mapping):
            return _failure("precondition_failed", "camera FOV reference action envelope is missing")
        request_json = str(arguments.get("request_json") or "")
        if not request_json:
            return _failure("precondition_failed", "camera FOV reference request JSON is missing")
        workflow = "camera_fov_reference"
        plan = self.execute(request, arguments={"command": "plan", "workflow": workflow, "cli_options": {"--request-json": request_json}}, cancel_event=cancel_event)
        if plan.get("status") != "passed":
            return plan
        plan_id = self._nested_value(plan.get("payload"), ("planId", "plan_id"))
        plan_revision = self._nested_value(plan.get("payload"), ("revision", "baseRevision", "base_revision"))
        approval_required = self._nested_value(plan.get("payload"), ("approvalRequired", "approval_required"))
        if not plan_id or not plan_revision or approval_required is not True:
            return _failure("not_observed", "UnityArtist plan did not expose an approval-bound plan and revision")
        expected_revision = str(arguments.get("expected_revision") or "")
        if expected_revision and str(plan_revision) != expected_revision:
            return _failure("precondition_failed", "UnityArtist plan revision does not match the approved inspection revision")
        preview = self.execute(
            request,
            arguments={"command": "preview", "workflow": workflow, "cli_options": {"--plan-id": str(plan_id), "--expected-revision": str(plan_revision)}},
            cancel_event=cancel_event,
        )
        if preview.get("status") != "passed":
            return preview
        apply_result = self.execute(
            request,
            arguments={
                "command": "apply",
                "workflow": workflow,
                "approval_token": str(arguments.get("approval_token") or ""),
                "expected_revision": str(plan_revision),
                "cli_options": {"--plan-id": str(plan_id), "--expected-revision": str(plan_revision)},
            },
            cancel_event=cancel_event,
        )
        if apply_result.get("status") != "passed":
            return apply_result
        target_name = str(arguments.get("target_name") or "Main Camera")
        capture = self.execute(
            request,
            arguments={"command": "capture", "workflow": workflow, "cli_options": {"--request-json": json.dumps({"captureCameraName": target_name}, separators=(",", ":"))}},
            cancel_event=cancel_event,
        )
        if capture.get("status") != "passed":
            return capture
        capture_evidence = self._nested_value(capture.get("payload"), ("evidence",)) or []
        capture_id = self._nested_value(capture.get("payload"), ("captureId", "capture_id"))
        color_path = ""
        if isinstance(capture_evidence, list):
            for item in capture_evidence:
                if isinstance(item, str) and item.startswith("color_path:"):
                    color_path = item.split(":", 1)[1]
                    break
        capture_summary = {
            "captureId": str(capture_id or ""),
            "colorPath": color_path,
            "evidence": list(capture_evidence) if isinstance(capture_evidence, list) else [],
        }
        apply_payload = apply_result.get("payload")
        apply_diff = self._nested_value(apply_payload, ("exactDiff", "exact_diff")) or {}
        before_value = self._nested_value(apply_diff, ("before",))
        after_value = self._nested_value(apply_diff, ("after",))
        observed_revision = self._nested_value(apply_payload, ("observedRevision", "observed_revision"))
        observed_target = str(self._nested_value(apply_diff, ("target",)) or "")
        expected_guid = str(arguments.get("target_guid") or reference.get("target", {}).get("guid", ""))
        expected_name = str(arguments.get("target_name") or "Main Camera")
        if not expected_guid or observed_target not in {expected_guid, expected_name}:
            return _failure("precondition_failed", "UnityArtist apply exact diff is not bound to the approved camera target")
        # Older cached Editor assemblies may report the camera name in the
        # exact diff while the request and adapter validation are already
        # GlobalObjectId-bound.  Normalize that compatibility representation
        # to the typed action's canonical target before Runtime validation.
        exact_target = expected_guid
        exact_diff = {
            "target": exact_target,
            "property": str(self._nested_value(apply_diff, ("property",)) or "Camera.fieldOfView"),
            "before": float(before_value) if before_value is not None else 0.0,
            "after": float(after_value) if after_value is not None else float(reference.get("value", 0.0)),
        }
        apply_summary = {
            "savePerformed": self._nested_value(apply_payload, ("savePerformed", "save_performed")) is True,
            "undoAvailable": self._nested_value(apply_payload, ("undoAvailable", "undo_available")) is True,
            "revision": str(observed_revision or self._nested_value(apply_payload, ("revision",)) or ""),
            "exactDiff": exact_diff,
            "evidence": self._nested_value(apply_payload, ("evidence",)) or [],
        }
        return {
            "status": "passed",
            "failure_class": None,
            "reason": None,
            "provider_ref": ARTIST_PROVIDER,
            "evidence": ["mutation_evidence", "editor_observation", "visual_capture", "exact_diff", "expected_revision", "camera_binding", "undo_registration", "save_not_performed"],
            "payload": {"plan": plan.get("payload"), "preview": preview.get("payload"), "apply": apply_summary, "capture": capture_summary},
            "apply": apply_summary,
            "capture": capture_summary,
            "before_value": exact_diff["before"],
            "after_value": exact_diff["after"],
            "observed_revision": str(observed_revision or self._nested_value(apply_payload, ("revision",)) or ""),
            "exact_diff": exact_diff,
        }

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
