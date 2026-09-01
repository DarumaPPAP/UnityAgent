"""Allowlisted Development/QA Player Runtime Provider.

Player transport is injected by the current Runtime environment. This module does
not implement a remote shell, select providers, or own durable Evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import yaml

from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Guardrails.tool_runtime_guard import guard_runtime_dispatch, mutation_scope_fingerprint
from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.capability_resolver import ResolutionContext

SUPPORTED_CAPABILITIES = frozenset({"player.observe", "player.mutate"})
ALLOWED_BUILD_KINDS = frozenset({"development", "qa"})
DEFAULT_CATALOG_PATH = Path(__file__).with_name("runtime_command_catalog.yaml")


@dataclass(frozen=True)
class PlayerBuildArtifact:
    artifact_id: str
    project_root: str
    build_kind: str
    command_surface_enabled: bool
    catalog_revision: str


@dataclass(frozen=True)
class RuntimeEndpointObservation:
    instance_id: str
    reachable: bool | str
    project_root: str | None
    artifact_id: str | None
    build_kind: str | None
    catalog_revision: str | None
    session_revision: str | None = None
    target_device_id: str | None = None


class PlayerRuntimeTransport(Protocol):
    def discover(self) -> Sequence[RuntimeEndpointObservation]:
        ...

    def invoke(
        self,
        *,
        instance_id: str,
        command_id: str,
        arguments: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class RuntimeCommand:
    command_id: str
    surface: str
    capability: str
    requires_approval: bool
    evidence: tuple[str, ...]
    evidence_class: str
    performance_dimension: str | None


def _failure(failure_class: str, reason: str, *, command_id: str | None = None) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_class": failure_class,
        "reason": reason,
        "provider_ref": "player_runtime",
        "command_id": command_id,
        "evidence": [],
        "verified": False,
    }


def _load_catalog(path: Path) -> tuple[str, dict[str, RuntimeCommand]]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if value.get("kind") != "player_runtime_command_catalog":
        raise ValueError("invalid Player Runtime command catalog kind")
    if value.get("release_surface_enabled") is not False:
        raise ValueError("Release Player command surface must be disabled")
    revision = str(value.get("catalog_revision") or "").strip()
    if not revision:
        raise ValueError("Player Runtime command catalog revision is required")

    raw_commands = value.get("commands")
    if not isinstance(raw_commands, dict) or not raw_commands:
        raise ValueError("Player Runtime command catalog must contain commands")

    commands: dict[str, RuntimeCommand] = {}
    for command_id, raw in raw_commands.items():
        if not isinstance(command_id, str) or not command_id.strip() or not isinstance(raw, dict):
            raise ValueError("invalid Player Runtime command entry")
        surface = str(raw.get("surface") or "")
        capability = str(raw.get("capability") or "")
        if surface not in {"observe", "control"}:
            raise ValueError(f"{command_id}: surface must be observe or control")
        expected_capability = "player.observe" if surface == "observe" else "player.mutate"
        if capability != expected_capability:
            raise ValueError(f"{command_id}: capability does not match command surface")
        requires_approval = raw.get("requires_approval")
        if not isinstance(requires_approval, bool):
            raise ValueError(f"{command_id}: requires_approval must be boolean")
        if surface == "control" and requires_approval is not True:
            raise ValueError(f"{command_id}: control commands must require explicit approval")
        raw_evidence = raw.get("evidence")
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise ValueError(f"{command_id}: evidence must be a non-empty list")
        evidence = tuple(str(item) for item in raw_evidence)
        required = {"player_observation"}
        if surface == "control":
            required.add("mutation_evidence")
        if not required.issubset(set(evidence)):
            raise ValueError(f"{command_id}: evidence contract is incomplete")
        evidence_class = str(raw.get("evidence_class") or "")
        if evidence_class not in {"runtime_observation", "target_performance_sample"}:
            raise ValueError(f"{command_id}: unsupported evidence_class {evidence_class!r}")
        performance_dimension = raw.get("performance_dimension")
        commands[command_id] = RuntimeCommand(
            command_id=command_id,
            surface=surface,
            capability=capability,
            requires_approval=requires_approval,
            evidence=evidence,
            evidence_class=evidence_class,
            performance_dimension=None if performance_dimension is None else str(performance_dimension),
        )
    return revision, commands


class PlayerRuntimeProvider:
    """Execute only allowlisted structured commands on one bound Development/QA Player."""

    def __init__(
        self,
        project_root: str | Path,
        environment_snapshot: dict[str, Any],
        *,
        build_artifact: PlayerBuildArtifact,
        transport: PlayerRuntimeTransport,
        catalog_path: Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve(strict=False)
        self.environment_snapshot = environment_snapshot
        self.build_artifact = build_artifact
        self.transport = transport
        self.catalog_revision, self.commands = _load_catalog(catalog_path or DEFAULT_CATALOG_PATH)

    def _surface_enabled(self) -> bool:
        return (
            self.build_artifact.build_kind in ALLOWED_BUILD_KINDS
            and self.build_artifact.command_surface_enabled is True
            and self.build_artifact.catalog_revision == self.catalog_revision
            and same_project_root(self.build_artifact.project_root, str(self.project_root))
        )

    def available_commands(self) -> tuple[str, ...]:
        if not self._surface_enabled():
            return ()
        return tuple(sorted(self.commands))

    def _validate_request(
        self,
        request: dict[str, Any],
        *,
        command: RuntimeCommand,
        context: ResolutionContext,
    ) -> dict[str, Any] | None:
        try:
            validate_capability_request(request)
            validate_environment_snapshot(self.environment_snapshot)
        except Exception as exc:
            return _failure(
                "precondition_failed",
                f"invalid Player Runtime contract: {exc}",
                command_id=command.command_id,
            )

        if request.get("capability") not in SUPPORTED_CAPABILITIES:
            return _failure(
                "unsupported",
                f"Player Runtime does not execute {request.get('capability')!r}",
                command_id=command.command_id,
            )
        if request.get("capability") != command.capability:
            return _failure(
                "unsupported",
                "command surface does not match requested Player capability",
                command_id=command.command_id,
            )
        if not same_project_root(str(request.get("project_root") or ""), str(self.project_root)):
            return _failure(
                "scope_violation",
                "CapabilityRequest project_root does not match Player Runtime Provider",
                command_id=command.command_id,
            )
        if not self._surface_enabled():
            return _failure(
                "unsupported",
                "Player command surface is available only for matching Development/QA build artifacts",
                command_id=command.command_id,
            )

        guard = guard_runtime_dispatch(request, self.environment_snapshot, context=context)
        if not guard.allowed:
            return _failure(
                str(guard.failure_class),
                str(guard.reason),
                command_id=command.command_id,
            )
        if command.requires_approval and (
            not request.get("approval_ref") or context.approval_complete is not True
        ):
            return _failure(
                "blocked_by_approval",
                "control command requires completed explicit approval",
                command_id=command.command_id,
            )
        return None

    def _bind_endpoint(self) -> tuple[RuntimeEndpointObservation | None, dict[str, Any] | None]:
        player_fact = self.environment_snapshot.get("player_runtime") or {}
        reachable = player_fact.get("reachable")
        if reachable == "unknown":
            return None, _failure("unknown", "Player Runtime reachability is unknown")
        if reachable is not True:
            return None, _failure("unavailable", "Player Runtime is unavailable")

        try:
            observed = list(self.transport.discover())
        except Exception as exc:
            return None, _failure("unhealthy", f"Player Runtime discovery failed: {exc}")
        if not observed:
            return None, _failure("unavailable", "no Player Runtime endpoint was discovered")

        matching: list[RuntimeEndpointObservation] = []
        unknown = False
        for item in observed:
            if item.reachable == "unknown":
                unknown = True
                continue
            if item.reachable is not True:
                continue
            if item.project_root is None or item.artifact_id is None:
                continue
            if not same_project_root(item.project_root, str(self.project_root)):
                continue
            if item.artifact_id != self.build_artifact.artifact_id:
                continue
            if item.build_kind != self.build_artifact.build_kind:
                continue
            if item.catalog_revision != self.catalog_revision:
                continue
            matching.append(item)

        expected_instance = player_fact.get("instance_id")
        if expected_instance:
            matching = [item for item in matching if item.instance_id == expected_instance]

        if len(matching) > 1:
            return None, _failure(
                "ambiguous_binding",
                "multiple Player Runtime endpoints match the requested Project/build",
            )
        if not matching:
            return None, _failure(
                "unknown" if unknown else "unavailable",
                "Player Runtime endpoint is not bound to the requested Project/build artifact",
            )
        endpoint = matching[0]
        if endpoint.build_kind not in ALLOWED_BUILD_KINDS:
            return None, _failure("unsupported", "Release Player command surface is not exposed")
        return endpoint, None

    @staticmethod
    def _normalize_transport_result(
        *,
        command: RuntimeCommand,
        endpoint: RuntimeEndpointObservation,
        result: Mapping[str, Any],
        scope_fingerprint: str | None,
    ) -> dict[str, Any]:
        transport_status = str(result.get("status") or "")
        if transport_status in {"disconnected", "unavailable"}:
            return _failure(
                "unavailable",
                "Player Runtime disconnected during command execution",
                command_id=command.command_id,
            )
        if transport_status == "timeout":
            return _failure("timeout", "Player Runtime command timed out", command_id=command.command_id)
        if transport_status == "cancelled":
            return _failure("cancelled", "Player Runtime command was cancelled", command_id=command.command_id)
        if transport_status not in {"passed", "failed"}:
            return _failure(
                "not_observed",
                "structured Player Runtime result status was not observed",
                command_id=command.command_id,
            )

        if result.get("instance_id") != endpoint.instance_id:
            return _failure(
                "ambiguous_binding",
                "Player Runtime response instance changed during execution",
                command_id=command.command_id,
            )
        if result.get("command_id") != command.command_id:
            return _failure(
                "execution_failed",
                "Player Runtime response command id does not match request",
                command_id=command.command_id,
            )
        result_project = result.get("project_root")
        if result_project is None or not same_project_root(
            str(result_project), str(endpoint.project_root or "")
        ):
            return _failure(
                "scope_violation",
                "Player Runtime response is bound to a different Project",
                command_id=command.command_id,
            )
        if result.get("artifact_id") != endpoint.artifact_id:
            return _failure(
                "precondition_failed",
                "Player Runtime response artifact identity changed during execution",
                command_id=command.command_id,
            )
        if endpoint.session_revision and result.get("session_revision") != endpoint.session_revision:
            return _failure(
                "precondition_failed",
                "Player Runtime session revision changed during execution",
                command_id=command.command_id,
            )

        payload = result.get("payload")
        if not isinstance(payload, dict):
            return _failure(
                "not_observed",
                "Player Runtime structured payload was not observed",
                command_id=command.command_id,
            )

        if transport_status == "failed":
            allowed_failure_classes = {
                "unavailable",
                "unknown",
                "unhealthy",
                "blocked_by_policy",
                "blocked_by_approval",
                "scope_violation",
                "unsupported",
                "backend_not_implemented",
                "precondition_failed",
                "execution_failed",
                "cancelled",
                "timeout",
                "observed_test_failure",
                "not_observed",
            }
            failure_class = str(result.get("failure_class") or "execution_failed")
            if failure_class not in allowed_failure_classes:
                failure_class = "execution_failed"
            return {
                **_failure(
                    failure_class,
                    str(result.get("reason") or "Player Runtime command failed"),
                    command_id=command.command_id,
                ),
                "payload": payload,
            }

        if command.surface == "control" and (
            payload.get("applied") is not True or "observed_state" not in payload
        ):
            return _failure(
                "not_observed",
                "control acknowledgement and observed_state are required for mutation evidence",
                command_id=command.command_id,
            )

        return {
            "status": "passed",
            "failure_class": None,
            "reason": None,
            "provider_ref": "player_runtime",
            "command_id": command.command_id,
            "instance_id": endpoint.instance_id,
            "target_device_id": endpoint.target_device_id,
            "session_revision": endpoint.session_revision,
            "payload": payload,
            "evidence": list(command.evidence),
            "evidence_class": command.evidence_class,
            "performance_dimension": command.performance_dimension,
            "mutation_scope_fingerprint": scope_fingerprint,
            "verified": True,
        }

    def execute(
        self,
        request: dict[str, Any],
        *,
        command_id: str,
        arguments: Mapping[str, Any] | None,
        context: ResolutionContext,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        if timeout_seconds <= 0:
            return _failure(
                "precondition_failed",
                "timeout_seconds must be greater than zero",
                command_id=command_id,
            )
        command = self.commands.get(command_id)
        if command is None:
            return _failure(
                "unsupported",
                f"unknown Player Runtime command: {command_id}",
                command_id=command_id,
            )
        failure = self._validate_request(request, command=command, context=context)
        if failure:
            return failure

        endpoint, failure = self._bind_endpoint()
        if failure:
            return {**failure, "command_id": command_id}
        assert endpoint is not None

        try:
            result = self.transport.invoke(
                instance_id=endpoint.instance_id,
                command_id=command.command_id,
                arguments=dict(arguments or {}),
                timeout_seconds=timeout_seconds,
            )
        except TimeoutError:
            return _failure("timeout", "Player Runtime command timed out", command_id=command_id)
        except Exception as exc:
            return _failure(
                "unhealthy",
                f"Player Runtime transport failed: {exc}",
                command_id=command_id,
            )

        if not isinstance(result, Mapping):
            return _failure(
                "not_observed",
                "Player Runtime transport did not return structured data",
                command_id=command_id,
            )
        return self._normalize_transport_result(
            command=command,
            endpoint=endpoint,
            result=result,
            scope_fingerprint=mutation_scope_fingerprint(request),
        )
