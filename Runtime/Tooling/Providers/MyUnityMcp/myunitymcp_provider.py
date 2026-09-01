"""Safe MyUnityMCP Editor Domain Provider adapter.

The adapter preserves MyUnityMCP's existing prepare/revision/approval/apply
contract. It never falls back to raw eval, generic serialized mutation, Save, or
Bake. Connector transport is injected so MyUnityMCP remains optional.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.Providers.MyUnityMcp.capability_mapper import (
    SEPARATE_APPROVAL_TOOLS,
    ToolDescriptor,
    available_capabilities as mapped_available_capabilities,
    materialize_capability_tools,
    mutation_workflow,
)
from Runtime.Tooling.Providers.MyUnityMcp.instance_binding import (
    MyUnityMcpBinding,
    MyUnityMcpInstanceObservation,
    bind_myunitymcp_instance,
)
from Runtime.Tooling.Providers.MyUnityMcp.result_mapper import (
    PreparedMutationProvenance,
    extract_prepared_mutation,
    normalize_tool_result,
    redacted_provenance,
)


class MyUnityMcpTransport(Protocol):
    def list_instances(self) -> Sequence[MyUnityMcpInstanceObservation | Mapping[str, Any]] | None: ...
    def list_tools(self, instance_id: str) -> Sequence[ToolDescriptor | Mapping[str, Any]]: ...
    def call_tool(
        self,
        instance_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        timeout_seconds: float,
        cancel_event: threading.Event | None = None,
    ) -> object: ...


def _failure(failure_class: str, reason: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_class": failure_class,
        "reason": reason,
        "provider_ref": "myunitymcp",
        "evidence": [],
    }


def _scope_digest(scope: Mapping[str, Any]) -> str:
    encoded = json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_intended_scope(scope: Mapping[str, Any] | None) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(scope, Mapping):
        return None, _failure("scope_violation", "intended Mutation Scope is required before MyUnityMCP prepare")
    allowed = scope.get("allowed_paths")
    prohibited = scope.get("prohibited_paths")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(item, str) and item for item in allowed):
        return None, _failure("scope_violation", "intended Mutation Scope requires non-empty allowed_paths")
    if not isinstance(prohibited, list) or not all(isinstance(item, str) and item for item in prohibited):
        return None, _failure("scope_violation", "intended Mutation Scope prohibited_paths must be a string list")
    for path in [*allowed, *prohibited]:
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            return None, _failure("scope_violation", f"unsafe Mutation Scope path: {path}")
    return _scope_digest(dict(scope)), None


class MyUnityMcpProvider:
    """Capability-local adapter over an injected live MyUnityMCP transport."""

    def __init__(
        self,
        project_root: str | Path,
        environment_snapshot: dict[str, Any],
        transport: MyUnityMcpTransport,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.environment_snapshot = environment_snapshot
        self.transport = transport

    def _instance_observations(self) -> Sequence[MyUnityMcpInstanceObservation] | None:
        try:
            raw = self.transport.list_instances()
        except (ConnectionError, PermissionError, OSError):
            return None
        if raw is None:
            return None
        result: list[MyUnityMcpInstanceObservation] = []
        for item in raw:
            if isinstance(item, MyUnityMcpInstanceObservation):
                result.append(item)
                continue
            if not isinstance(item, Mapping):
                continue
            instance_id = item.get("instance_id") or item.get("instanceId") or item.get("id")
            reachable = item.get("reachable", "unknown")
            project_root = item.get("project_root") or item.get("projectRoot")
            enabled = item.get("enabled_tools") or item.get("enabledTools") or ()
            if isinstance(instance_id, str) and instance_id:
                result.append(
                    MyUnityMcpInstanceObservation(
                        instance_id=instance_id,
                        reachable=reachable if reachable in (True, False, "unknown") else "unknown",
                        project_root=str(project_root) if project_root else None,
                        enabled_tools=tuple(str(value) for value in enabled if isinstance(value, str)),
                    )
                )
        return result

    def binding(self) -> MyUnityMcpBinding:
        return bind_myunitymcp_instance(str(self.project_root), self._instance_observations())

    def _binding_failure(self) -> tuple[str | None, dict[str, Any] | None]:
        binding = self.binding()
        if binding.binding_status == "ambiguous_binding":
            return None, _failure("ambiguous_binding", "multiple MyUnityMCP instances are bound to this project")
        if binding.binding_status == "unknown":
            return None, _failure("unknown", "MyUnityMCP project binding is unknown")
        if binding.binding_status != "bound" or not binding.bound_instance_id:
            return None, _failure("unavailable", "MyUnityMCP is not bound to the requested project")

        snapshot = self.environment_snapshot.get("myunitymcp") or {}
        snapshot_instance = snapshot.get("bound_instance_id")
        if snapshot_instance and snapshot_instance != binding.bound_instance_id:
            return None, _failure("ambiguous_binding", "live MyUnityMCP instance differs from Environment Snapshot binding")
        return binding.bound_instance_id, None

    def discover_tools(self) -> tuple[ToolDescriptor, ...]:
        instance_id, failure = self._binding_failure()
        if failure or instance_id is None:
            return ()
        try:
            raw = self.transport.list_tools(instance_id)
        except (ConnectionError, PermissionError, OSError):
            return ()

        result: list[ToolDescriptor] = []
        for item in raw:
            if isinstance(item, ToolDescriptor):
                result.append(item)
                continue
            if not isinstance(item, Mapping):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                continue
            group = item.get("group")
            schema = item.get("input_schema") or item.get("inputSchema")
            result.append(
                ToolDescriptor(
                    name=name,
                    group=str(group) if group is not None else None,
                    input_schema=schema if isinstance(schema, Mapping) else None,
                )
            )
        return tuple(result)

    def available_capabilities(self) -> frozenset[str]:
        discovered = mapped_available_capabilities(self.discover_tools())
        return frozenset(value for value in discovered if value != "domain.workflow")

    def materialize_tools(
        self,
        capability: str,
        *,
        workflow_key: str | None = None,
    ) -> tuple[ToolDescriptor, ...]:
        return materialize_capability_tools(
            capability,
            self.discover_tools(),
            workflow_key=workflow_key,
        )

    def _validate_common(
        self,
        request: dict[str, Any],
        *,
        expected_capability: str,
        policy_allowed: bool,
        approval_required: bool,
        approval_complete: bool,
    ) -> tuple[str | None, dict[str, Any] | None]:
        try:
            validate_capability_request(request)
            validate_environment_snapshot(self.environment_snapshot)
        except Exception as exc:
            return None, _failure("precondition_failed", f"invalid runtime contract: {exc}")

        if request.get("capability") != expected_capability:
            return None, _failure(
                "unsupported",
                f"MyUnityMCP Provider expected {expected_capability!r}, got {request.get('capability')!r}",
            )
        if not same_project_root(str(request.get("project_root") or ""), str(self.project_root)):
            return None, _failure("scope_violation", "CapabilityRequest project_root does not match MyUnityMCP Provider")
        snapshot_root = str((self.environment_snapshot.get("project") or {}).get("root") or "")
        if not snapshot_root or not same_project_root(snapshot_root, str(self.project_root)):
            return None, _failure("scope_violation", "Environment Snapshot is bound to a different project")
        if not policy_allowed:
            return None, _failure("blocked_by_policy", "Policy denied MyUnityMCP execution")

        snapshot = self.environment_snapshot.get("myunitymcp") or {}
        if snapshot.get("binding_status") == "ambiguous_binding":
            return None, _failure("ambiguous_binding", "Environment Snapshot has ambiguous MyUnityMCP binding")
        if snapshot.get("available") is not True or snapshot.get("project_bound") is not True:
            return None, _failure("unavailable", "Environment Snapshot does not prove MyUnityMCP project binding")
        if snapshot.get("binding_status") != "bound":
            return None, _failure("unavailable", f"MyUnityMCP binding status is {snapshot.get('binding_status')!r}")

        if approval_required:
            if not request.get("approval_ref") or not approval_complete:
                return None, _failure("blocked_by_approval", "required UnityAgent approval is not complete")

        instance_id, failure = self._binding_failure()
        if failure:
            return None, failure
        return instance_id, None

    def _safe_mode_failure(self) -> dict[str, Any] | None:
        editor = self.environment_snapshot.get("unity_editor") or {}
        if editor.get("safe_mode") is True:
            return _failure("precondition_failed", "MyUnityMCP mutation is blocked while Unity is in Safe Mode")
        if editor.get("running") is True and editor.get("safe_mode") == "unknown":
            return _failure("not_observed", "running Editor Safe Mode state is unknown")
        return None

    def _call(
        self,
        instance_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        timeout_seconds: float,
        cancel_event: threading.Event | None,
    ) -> tuple[object | None, dict[str, Any] | None]:
        if cancel_event is not None and cancel_event.is_set():
            return None, _failure("cancelled", "MyUnityMCP execution was cancelled before dispatch")
        try:
            raw = self.transport.call_tool(
                instance_id,
                tool_name,
                dict(arguments),
                timeout_seconds=timeout_seconds,
                cancel_event=cancel_event,
            )
        except TimeoutError:
            return None, _failure("timeout", f"MyUnityMCP tool {tool_name} timed out")
        except PermissionError:
            return None, _failure("unavailable", f"MyUnityMCP tool {tool_name} is not permitted")
        except ConnectionError:
            return None, _failure("unavailable", f"MyUnityMCP disconnected while calling {tool_name}")
        except OSError as exc:
            return None, _failure("unhealthy", f"MyUnityMCP transport failed: {exc}")
        return raw, None

    def _observe_revision(
        self,
        instance_id: str,
        *,
        timeout_seconds: float,
        cancel_event: threading.Event | None,
    ) -> tuple[tuple[str, int] | None, dict[str, Any] | None]:
        tools = {tool.name for tool in self.discover_tools()}
        if "graphics.inspect_project" not in tools:
            return None, _failure("unsupported", "graphics.inspect_project is not exposed")
        raw, failure = self._call(
            instance_id,
            "graphics.inspect_project",
            {},
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return None, failure
        normalized = normalize_tool_result(raw)
        if normalized["status"] != "passed":
            return None, normalized
        structured = normalized["structured_result"]
        session_id = structured.get("sessionId")
        revision = structured.get("revision")
        if not isinstance(session_id, str) or not session_id or not isinstance(revision, int):
            return None, _failure("not_observed", "MyUnityMCP project inspection did not expose session/revision")
        return (session_id, revision), None

    def run_read(
        self,
        request: dict[str, Any],
        *,
        policy_allowed: bool,
        tool_name: str | None = None,
        arguments: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        capability = str(request.get("capability") or "")
        if capability not in {"project.inspect", "scene.inspect", "profiler.observe", "visual.capture"}:
            return _failure("unsupported", f"MyUnityMCP read adapter does not execute {capability!r}")
        instance_id, failure = self._validate_common(
            request,
            expected_capability=capability,
            policy_allowed=policy_allowed,
            approval_required=False,
            approval_complete=False,
        )
        if failure or instance_id is None:
            return failure or _failure("unavailable", "MyUnityMCP instance unavailable")

        materialized = self.materialize_tools(capability)
        if not materialized:
            return _failure("unsupported", f"required MyUnityMCP tool group for {capability} is not exposed")
        selected = tool_name or materialized[0].name
        allowed = {tool.name for tool in materialized}
        if selected not in allowed:
            return _failure("unsupported", f"MyUnityMCP tool {selected!r} is not materialized for {capability}")

        raw, failure = self._call(
            instance_id,
            selected,
            arguments or {},
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure
        evidence = {
            "project.inspect": ("project_fact",),
            "scene.inspect": ("editor_observation",),
            "profiler.observe": ("profiler_observation",),
            "visual.capture": ("visual_capture",),
        }[capability]
        return normalize_tool_result(raw, evidence=evidence)

    def prepare_mutation(
        self,
        request: dict[str, Any],
        *,
        workflow_key: str,
        intended_mutation_scope: Mapping[str, Any],
        prepare_arguments: Mapping[str, Any],
        policy_allowed: bool,
        timeout_seconds: float = 30.0,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Prepare Exact Diff under a read-only scene.inspect substep."""
        instance_id, failure = self._validate_common(
            request,
            expected_capability="scene.inspect",
            policy_allowed=policy_allowed,
            approval_required=False,
            approval_complete=False,
        )
        if failure or instance_id is None:
            return failure or _failure("unavailable", "MyUnityMCP instance unavailable")

        scope_digest, failure = _validate_intended_scope(intended_mutation_scope)
        if failure or scope_digest is None:
            return failure or _failure("scope_violation", "invalid intended Mutation Scope")

        try:
            workflow = mutation_workflow(workflow_key)
        except ValueError:
            return _failure("unsupported", f"MyUnityMCP mutation workflow {workflow_key!r} is not allowlisted")
        if workflow.prepare_tool in SEPARATE_APPROVAL_TOOLS or workflow.apply_tool in SEPARATE_APPROVAL_TOOLS:
            return _failure("unsupported", "Save/Bake cannot be folded into scene.mutate approval")

        tools = self.materialize_tools("scene.mutate", workflow_key=workflow_key)
        if not tools:
            return _failure("unsupported", f"MyUnityMCP workflow {workflow_key!r} is not currently exposed")
        tool_names = {tool.name for tool in tools}
        if workflow.prepare_tool not in tool_names or workflow.apply_tool not in tool_names:
            return _failure("unsupported", "prepare/apply tool group is incomplete")

        observed, failure = self._observe_revision(
            instance_id,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure or observed is None:
            return failure or _failure("not_observed", "current Editor revision unavailable")
        session_id, revision = observed

        arguments = dict(prepare_arguments)
        if "approvalToken" in arguments or "planId" in arguments:
            return _failure("precondition_failed", "prepare arguments cannot supply apply provenance")
        supplied_revision = arguments.get("expectedRevision")
        if supplied_revision is not None and supplied_revision != revision:
            return _failure("precondition_failed", "prepare expectedRevision does not match current Editor revision")
        arguments["expectedRevision"] = revision

        raw, failure = self._call(
            instance_id,
            workflow.prepare_tool,
            arguments,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure
        provenance, normalized = extract_prepared_mutation(
            raw,
            workflow_key=workflow_key,
            prepare_tool=workflow.prepare_tool,
            apply_tool=workflow.apply_tool,
            approval_group=workflow.approval_group,
            instance_id=instance_id,
            mutation_scope_digest=scope_digest,
        )
        if provenance is None:
            return normalized
        if provenance.session_id != session_id or provenance.expected_revision != revision:
            return _failure("precondition_failed", "prepare result provenance does not match inspected Editor session/revision")

        return {
            **normalized,
            "provider_ref": "myunitymcp",
            "provenance": provenance,
            "redacted_provenance": redacted_provenance(provenance),
            "evidence": ["editor_observation"],
        }

    def apply_prepared_mutation(
        self,
        request: dict[str, Any],
        *,
        provenance: PreparedMutationProvenance,
        apply_arguments: Mapping[str, Any] | None,
        policy_allowed: bool,
        approval_complete: bool,
        timeout_seconds: float = 30.0,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        instance_id, failure = self._validate_common(
            request,
            expected_capability="scene.mutate",
            policy_allowed=policy_allowed,
            approval_required=True,
            approval_complete=approval_complete,
        )
        if failure or instance_id is None:
            return failure or _failure("unavailable", "MyUnityMCP instance unavailable")

        safe_mode = self._safe_mode_failure()
        if safe_mode:
            return safe_mode

        if provenance.instance_id != instance_id:
            return _failure("ambiguous_binding", "prepared mutation belongs to a different MyUnityMCP instance")

        try:
            workflow = mutation_workflow(provenance.workflow_key)
        except ValueError:
            return _failure("unsupported", "prepared MyUnityMCP workflow is no longer allowlisted")
        if workflow.prepare_tool != provenance.prepare_tool or workflow.apply_tool != provenance.apply_tool:
            return _failure("precondition_failed", "prepared mutation tool provenance does not match canonical workflow")
        if workflow.approval_group != provenance.approval_group:
            return _failure("blocked_by_approval", "prepared mutation approval group changed")
        if workflow.apply_tool in SEPARATE_APPROVAL_TOOLS:
            return _failure("unsupported", "Save/Bake require separate approval boundaries")

        scope = request.get("mutation_scope")
        if not isinstance(scope, Mapping):
            return _failure("scope_violation", "scene.mutate request is missing Mutation Scope")
        if _scope_digest(dict(scope)) != provenance.mutation_scope_digest:
            return _failure("scope_violation", "Mutation Scope differs from the scope frozen at prepare time")

        tools = self.materialize_tools("scene.mutate", workflow_key=provenance.workflow_key)
        if not tools or workflow.apply_tool not in {tool.name for tool in tools}:
            return _failure("unsupported", "prepared MyUnityMCP apply tool is no longer exposed")

        observed, failure = self._observe_revision(
            instance_id,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure or observed is None:
            return failure or _failure("not_observed", "current Editor revision unavailable")
        session_id, revision = observed
        if session_id != provenance.session_id:
            return _failure("precondition_failed", "Editor Session changed after MyUnityMCP prepare")
        if revision != provenance.expected_revision:
            return _failure("precondition_failed", "Editor Revision changed after MyUnityMCP prepare")

        arguments = dict(apply_arguments or {})
        for protected in ("planId", "expectedRevision", "approvalToken"):
            if protected in arguments:
                return _failure("precondition_failed", f"apply arguments cannot override {protected}")
        arguments["planId"] = provenance.plan_id
        arguments["expectedRevision"] = provenance.expected_revision
        arguments["approvalToken"] = provenance.approval_token

        if workflow.apply_tool == "graphics.apply_plan":
            save_mode = arguments.get("saveMode")
            if save_mode not in (None, "NONE"):
                return _failure("unsupported", "graphics.apply_plan cannot merge Save into mutation approval")
            arguments["saveMode"] = "NONE"

        raw, failure = self._call(
            instance_id,
            workflow.apply_tool,
            arguments,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        if failure:
            return failure

        normalized = normalize_tool_result(
            raw,
            evidence=("editor_observation", "mutation_evidence"),
        )
        if normalized["status"] != "passed":
            return normalized
        return {
            **normalized,
            "redacted_provenance": redacted_provenance(provenance),
        }

    def run_domain_workflow(self, *_: Any, **__: Any) -> dict[str, Any]:
        """Fail closed until a pre-approval Agent graph handoff is canonicalized."""
        return _failure(
            "backend_not_implemented",
            "domain.workflow requires staged pre-approval Agent graph provenance; raw one-shot execution is prohibited",
        )
