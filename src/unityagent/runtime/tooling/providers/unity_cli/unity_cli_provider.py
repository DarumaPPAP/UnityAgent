"""Unity公式CLIをoptional structured Providerとして実行する。"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Any, Callable
from jsonschema.exceptions import ValidationError

from unityagent.runtime.contracts.capability_contract import validate_capability_request
from unityagent.runtime.dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from unityagent.runtime.tooling.environment.environment_snapshot import validate_environment_snapshot
from unityagent.runtime.tooling.environment.project_identity import same_project_root
from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand, build_artist_pipeline_command
from unityagent.runtime.tooling.providers.unity_cli.artist_result_mapper import artist_failure, matches_artist_project, normalize_artist_pipeline_result
from unityagent.runtime.tooling.providers.unity_cli.command_builder import (
    UnityCliCommand,
    build_compile_observation_command,
    build_pipeline_catalog_command,
    build_pipeline_command,
    build_project_build_command,
    build_test_command,
)
from unityagent.runtime.tooling.providers.unity_cli.discovery import (
    UnityCliSurfaceDiscovery,
    discover_unity_cli_surface,
)
from unityagent.runtime.tooling.providers.unity_cli.profiler_observation import ProfilerObservationError, normalize_profiler_observation
from unityagent.runtime.tooling.providers.unity_cli.result_mapper import (
    extract_command_catalog,
    is_finite_number,
    normalize_build_execution,
    normalize_compile_observation,
    normalize_pipeline_command,
    normalize_test_execution,
    parse_json_sequence,
)

SUPPORTED_CAPABILITIES = frozenset(
    {
        "project.inspect",
        "compile.observe",
        "project.test",
        "project.build",
        "scene.inspect",
        "profiler.observe",
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
        editor = self.environment_snapshot.get("unity_editor") or {}
        if discovery.pipeline_reachable is True and "get_performance_stats" in catalog_names and editor.get("running") is True and editor.get("project_bound") is True and editor.get("safe_mode") is False:
            result.add("profiler.observe")
        artist = self.environment_snapshot.get("artist") or {}
        if all(artist.get(key) is True for key in ("available", "compatible", "project_bound", "package_installed", "pipeline_reachable")):
            if "artist.inspect" in catalog_names:
                result.add("scene.inspect")
            if "artist.capture" in catalog_names:
                result.add("visual.capture")
            if {"artist." + name for name in ("inspect", "plan", "preview", "apply", "capture", "evaluate", "refine", "history", "cinematic")}.issubset(catalog_names):
                result.add("domain.workflow")
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

    def run_artist_read_only(self, request: dict[str, Any], *, command: ArtistCommand, timeout_seconds: float, policy_allowed: bool, expected_context_id: str | None = None, expected_context_fingerprint: str | None = None, cancel_event: threading.Event | None = None) -> dict[str, Any]:
        """既存観測APIの範囲を維持し、実行処理を共通入口へ渡す。"""
        try:
            build_artist_pipeline_command("unity", self.project_root, command)
        except PermissionError as exc:
            return artist_failure("blocked_by_approval", str(exc))
        except (TypeError, ValueError) as exc:
            return artist_failure("precondition_failed", str(exc))
        if command.name not in {"inspect", "history", "capture", "cinematic"} or command.name == "cinematic" and (command.operation or "inspect") != "inspect":
            return artist_failure("not_observed", "observation API does not execute workflow steps")
        return self.run_artist(request, command=command, timeout_seconds=timeout_seconds, policy_allowed=policy_allowed, expected_context_id=expected_context_id, expected_context_fingerprint=expected_context_fingerprint, cancel_event=cancel_event, require_context=False)

    def run_artist(self, request: dict[str, Any], *, command: ArtistCommand, timeout_seconds: float, policy_allowed: bool, expected_context_id: str | None = None, expected_context_fingerprint: str | None = None, expected_run_id: str | None = None, authority=None, approval_complete: bool = False, require_context: bool = True, cancel_event: threading.Event | None = None) -> dict[str, Any]:
        """型付き全9操作を同じProject／Policy／Context境界で実行する。"""
        authorization = None
        if authority is not None:
            authorization = {**authority.binding, "token": authority.token, "sessionId": authority.session_id, "reservationId": authority.reservation_id}
        try:
            built = build_artist_pipeline_command(str((self.environment_snapshot.get("unity_cli") or {}).get("executable_path") or ""), self.project_root, command, authorization=authorization)
            validate_capability_request(request)
            validate_environment_snapshot(self.environment_snapshot)
        except PermissionError as exc:
            return artist_failure("blocked_by_approval", str(exc))
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return artist_failure("precondition_failed", f"invalid Artist request: {exc}")
        if not policy_allowed:
            return artist_failure("blocked_by_policy", "Policy denied Artist execution")
        mutation = command.name == "apply" or command.name == "cinematic" and command.operation == "apply"
        expected_capability = "domain.workflow" if mutation else "visual.capture" if command.name == "capture" else "scene.inspect"
        scope_present = request.get("mutation_scope") is not None
        if request.get("capability") != expected_capability or request.get("operation_kind") != ("editor_mutation" if mutation else "read") or scope_present is not mutation:
            return artist_failure("scope_violation", "Artist command does not match its Capability and mutation scope")
        if mutation or command.name == "evaluate":
            if not request.get("approval_ref") or approval_complete is not True or authority is None:
                return artist_failure("blocked_by_approval", "Artist operation requires a live Control Plane approval")
            if authorization.get("runId") != expected_run_id or authorization.get("receivedContextId") != expected_context_id or authorization.get("receivedContextFingerprint") != expected_context_fingerprint:
                return artist_failure("scope_violation", "Artist authorization and current Context do not match")
        if require_context and (not expected_context_id or not expected_context_fingerprint or not expected_run_id or command.context_json is None):
            return artist_failure("not_observed", "Production Artist execution requires materialized Context and Run bindings")
        if command.context_json is not None:
            received = parse_json_sequence(command.context_json, strict=True)[0]
            if received["contextId"] != expected_context_id or received["contextFingerprint"] != expected_context_fingerprint or received["runId"] != expected_run_id or not matches_artist_project(received["projectRoot"], self.project_root):
                return artist_failure("scope_violation", "Command Context differs from the materialized Runtime Context")
        prohibited_evidence = set()
        if not mutation:
            prohibited_evidence.add("mutation_evidence")
        if command.name != "evaluate":
            prohibited_evidence.add("human_review_decision")
        if command.name != "capture":
            prohibited_evidence.add("visual_capture")
        if set(request["required_evidence"]).intersection(prohibited_evidence):
            return artist_failure("scope_violation", "read-only Artist request requires evidence outside its scope")
        if command.name == "capture":
            capture_request = parse_json_sequence(command.request_json, strict=True)[0] if command.request_json else {}
            camera = capture_request.get("captureCameraName")
            if not isinstance(camera, str) or not camera.strip():
                return artist_failure("precondition_failed", "Capture requires an explicit camera before dispatch")
        domain = (request.get("qualifiers") or {}).get("domain")
        allowed_domains = {"cinematic"} if command.name == "cinematic" else {"visual_art"} if command.name in {"plan", "preview", "apply"} else {"visual_art", "cinematic"}
        if domain not in allowed_domains:
            return artist_failure("scope_violation", "Artist command does not match requested domain")
        snapshot_root = (self.environment_snapshot.get("project") or {}).get("root")
        if not matches_artist_project(request["project_root"], self.project_root) or not matches_artist_project(snapshot_root, self.project_root):
            return artist_failure("scope_violation", "Artist request and Environment Snapshot must bind to this Project")
        if cancel_event is not None and cancel_event.is_set():
            return artist_failure("cancelled", "Artist command was cancelled before transport")
        if not is_finite_number(timeout_seconds) or timeout_seconds <= 0:
            return artist_failure("precondition_failed", "timeout_seconds must be finite and greater than zero")
        editor = self.environment_snapshot.get("unity_editor") or {}
        artist = self.environment_snapshot.get("artist") or {}
        cli = self.environment_snapshot.get("unity_cli") or {}
        if cli.get("available") is not True or editor.get("running") is not True or editor.get("project_bound") is not True or editor.get("safe_mode") is not False or editor.get("project_version_match") is not True:
            return artist_failure("unavailable", "Artist requires an available CLI and bound Editor outside Safe Mode")
        if any(artist.get(key) is not True for key in ("available", "package_installed", "compatible", "project_bound", "pipeline_reachable")):
            return artist_failure("not_observed", "Artist Package, compatibility and Pipeline binding are not observed")
        discovery, failure = self._require_discovery("command")
        if failure:
            return failure
        if discovery is None:
            return artist_failure("not_observed", "Artist Pipeline discovery returned no surface")
        if discovery.pipeline_reachable is not True:
            return artist_failure(
                discovery.failure_class or ("unavailable" if discovery.pipeline_reachable is False else "not_observed"),
                "Artist Pipeline discovery is unavailable: "
                f"pipeline_reachable={discovery.pipeline_reachable}, "
                f"catalog_status={discovery.status}, "
                f"project_info_observed={isinstance(discovery.project_info, dict)}, "
                f"reason={discovery.reason}",
            )
        if not isinstance(discovery.project_info, dict):
            return artist_failure("not_observed", "Artist Pipeline discovery did not observe current Project info")
        root = next((discovery.project_info.get(key) for key in ("path", "projectPath", "project_path", "root") if discovery.project_info.get(key)), None)
        status = discovery.editor_status
        instances = status.get("instances") if isinstance(status, dict) else status
        if not matches_artist_project(root, self.project_root):
            return artist_failure("scope_violation", "observed CLI Project identity is missing or mismatched")
        if not isinstance(instances, list):
            return artist_failure("not_observed", "Target Project Editor status was not observed")
        bound = [item for item in instances if isinstance(item, dict) and matches_artist_project(item.get("projectPath") or item.get("project"), self.project_root) and item.get("state") == "ready"]
        version = (self.environment_snapshot.get("project") or {}).get("unity_version")
        # Headless EditorはCLI statusへ登録されないため、空一覧だけは独立した実Process観測と対象Pipeline応答を照合する。
        process_bound = not instances and editor.get("binding_status") == "bound" and bool(editor.get("bound_instance_id")) and editor.get("version") == version and artist.get("binding_status") == "bound" and bool(artist.get("bound_instance_id"))
        listed_bound = len(bound) == 1 and (bound[0].get("version") or bound[0].get("editorVersion")) == version
        if not (process_bound or listed_bound) or not version or artist.get("unity_version") != version:
            return artist_failure("not_observed", "unique ready Editor with matching Unity version was not observed")
        entries = [item for item in discovery.command_catalog if item.get("name") == f"artist.{command.name}"]
        if len(entries) != 1 or entries[0].get("runtime_only") is not False:
            return artist_failure("unsupported", "Artist command is missing, ambiguous or runtime-only in the current Catalog")
        if cancel_event is not None and cancel_event.is_set():
            return artist_failure("cancelled", "Artist command was cancelled during discovery")
        exit_code, stdout, failure = self._dispatch(built, timeout_seconds=timeout_seconds, cancel_event=cancel_event)
        if failure:
            return failure
        if authority is not None:
            authorization["reservationId"] = authority.reservation_id
        result = normalize_artist_pipeline_result(exit_code=int(exit_code), stdout=stdout, command=command, project_root=self.project_root, unity_version=version, render_pipeline=artist.get("render_pipeline"), expected_context_id=expected_context_id, expected_context_fingerprint=expected_context_fingerprint, expected_run_id=expected_run_id, authorization=authorization)
        if result["status"] == "passed" and not set(request["required_evidence"]).issubset(result["evidence"]):
            return artist_failure("not_observed", "Artist result does not contain all requested evidence")
        return result

    def execute(self, request: dict[str, Any], context=None, arguments=None) -> dict[str, Any]:
        """ToolBrokerの標準executor署名。専門ContextはDispatcherから受領する。"""
        arguments = arguments or {}
        command = arguments.get("artist_command")
        if not isinstance(command, ArtistCommand):
            return artist_failure("precondition_failed", "Artist executor requires a typed command")
        payload = arguments.get("specialist_execution_context") or {}
        return self.run_artist(request, command=command, timeout_seconds=arguments.get("timeout_seconds", 60.0), policy_allowed=getattr(context, "policy_allowed", False), approval_complete=getattr(context, "approval_complete", False), expected_context_id=payload.get("context_id"), expected_context_fingerprint=payload.get("context_fingerprint"), expected_run_id=payload.get("run_id"), authority=arguments.get("artist_authority"), cancel_event=arguments.get("cancel_event"))

    def run_profiler_observe(
        self,
        request: dict[str, Any],
        *,
        timeout_seconds: float,
        policy_allowed: bool,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        failure = self._validate_common(request, expected_capability="profiler.observe", policy_allowed=policy_allowed, approval_required=False, approval_complete=False)
        if failure:
            return failure
        editor = self.environment_snapshot.get("unity_editor") or {}
        if editor.get("running") is not True or editor.get("project_bound") is not True or editor.get("safe_mode") is not False:
            return _failure("not_observed", "a running, project-bound Editor outside Safe Mode is required")
        discovery, failure = self._require_discovery("command")
        if failure:
            return failure
        if discovery is None or discovery.pipeline_reachable is not True:
            return _failure("unavailable", "Unity Pipeline is not observed reachable for this project")
        if not any(item.get("name") == "get_performance_stats" and item.get("runtime_only") is not True for item in discovery.command_catalog):
            return _failure("unsupported", "get_performance_stats is not exposed by the bound Editor")

        cli = self.environment_snapshot.get("unity_cli") or {}
        command = build_pipeline_command(str(cli["executable_path"]), self.project_root, "get_performance_stats")
        exit_code, stdout, failure = self._dispatch(command, timeout_seconds=timeout_seconds, cancel_event=cancel_event)
        if failure:
            return failure
        normalized = normalize_pipeline_command(exit_code=int(exit_code), stdout=stdout, evidence=["profiler_observation"])
        if normalized["status"] != "passed":
            return {**normalized, "provider_ref": "unity_cli"}
        try:
            observation = normalize_profiler_observation(normalized["result"], unity_version=str((self.environment_snapshot.get("project") or {}).get("unity_version") or "unknown"))
        except ProfilerObservationError as exc:
            return _failure("execution_failed", str(exc))
        return {"status": "passed", "failure_class": None, "reason": None, "provider_ref": "unity_cli", "evidence": ["profiler_observation"], **observation}

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
