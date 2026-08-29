"""Approved external Operations control API for Runtime.

This is distinct from Runtime/ExecutionControl, which owns hard execution safety.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


RUNTIME_OPERATION_APIS = {
    "pause": "runtime.operations.pause",
    "resume": "runtime.operations.resume",
    "stop": "runtime.operations.stop",
    "quarantine": "runtime.operations.quarantine",
    "switch_model": "runtime.operations.switch_model",
}


class RuntimeOperationsControlError(ValueError):
    pass


class RuntimeOperationsAPI:
    def __init__(self, handlers: dict[str, Callable[[dict[str, Any]], Any]]):
        self._handlers = dict(handlers)

    def handle(self, command: dict[str, Any]) -> Any:
        if command.get("schema_version") != "1.0" or not command.get("command_id"):
            raise RuntimeOperationsControlError("Runtime Operations API accepts approved commands only")
        if command.get("target_authority") != "Runtime":
            raise RuntimeOperationsControlError("command is not targeted at Runtime")
        action = str(command.get("action") or "")
        expected_api = RUNTIME_OPERATION_APIS.get(action)
        if expected_api is None or command.get("target_api") != expected_api:
            raise RuntimeOperationsControlError("unsupported or mismatched Runtime operational action")
        if not command.get("authorization_hash") or not command.get("policy_revision"):
            raise RuntimeOperationsControlError("approved command lacks authorization provenance")
        if command.get("approval_status") not in {"approved", "not_required"}:
            raise RuntimeOperationsControlError("approved command lacks valid approval outcome")
        handler = self._handlers.get(action)
        if handler is None:
            raise RuntimeOperationsControlError(f"Runtime handler unavailable: {action}")
        return handler(deepcopy(command))
