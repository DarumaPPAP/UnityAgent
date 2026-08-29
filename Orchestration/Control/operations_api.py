"""Approved external Operations control API for Orchestration semantics."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


ORCHESTRATION_OPERATION_APIS = {
    "disable_route": "orchestration.operations.disable_route",
    "force_hitl": "orchestration.operations.force_hitl",
    "replay_checkpoint": "orchestration.operations.replay_checkpoint",
}


class OrchestrationOperationsControlError(ValueError):
    pass


class OrchestrationOperationsAPI:
    def __init__(self, handlers: dict[str, Callable[[dict[str, Any]], Any]]):
        self._handlers = dict(handlers)

    def handle(self, command: dict[str, Any]) -> Any:
        if command.get("schema_version") != "1.0" or not command.get("command_id"):
            raise OrchestrationOperationsControlError("Orchestration Operations API accepts approved commands only")
        if command.get("target_authority") != "Orchestration":
            raise OrchestrationOperationsControlError("command is not targeted at Orchestration")
        action = str(command.get("action") or "")
        expected_api = ORCHESTRATION_OPERATION_APIS.get(action)
        if expected_api is None or command.get("target_api") != expected_api:
            raise OrchestrationOperationsControlError("unsupported or mismatched Orchestration operational action")
        if not command.get("authorization_hash") or not command.get("policy_revision"):
            raise OrchestrationOperationsControlError("approved command lacks authorization provenance")
        if command.get("approval_status") not in {"approved", "not_required"}:
            raise OrchestrationOperationsControlError("approved command lacks valid approval outcome")
        if action == "disable_route" and not (command.get("route_id") or (command.get("parameters") or {}).get("route_id")):
            raise OrchestrationOperationsControlError("disable_route requires route_id")
        if action == "replay_checkpoint":
            parameters = command.get("parameters") if isinstance(command.get("parameters"), dict) else {}
            if not parameters.get("checkpoint_id") or not parameters.get("resume_decision_ref"):
                raise OrchestrationOperationsControlError("replay_checkpoint requires checkpoint_id and resume_decision_ref")
        handler = self._handlers.get(action)
        if handler is None:
            raise OrchestrationOperationsControlError(f"Orchestration handler unavailable: {action}")
        return handler(deepcopy(command))
