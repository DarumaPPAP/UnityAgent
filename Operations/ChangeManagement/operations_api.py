"""Approved Operations rollback/config control API."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


class ChangeManagementControlError(ValueError):
    pass


class ChangeManagementOperationsAPI:
    def __init__(self, rollback_handler: Callable[[dict[str, Any]], Any]):
        self._rollback_handler = rollback_handler

    def handle(self, command: dict[str, Any]) -> Any:
        if command.get("schema_version") != "1.0" or not command.get("command_id"):
            raise ChangeManagementControlError("ChangeManagement API accepts approved commands only")
        if command.get("target_authority") != "ChangeManagement":
            raise ChangeManagementControlError("command is not targeted at ChangeManagement")
        if command.get("action") != "rollback_config" or command.get("target_api") != "operations.change_management.rollback_config":
            raise ChangeManagementControlError("unsupported ChangeManagement operational action")
        if not command.get("authorization_hash") or not command.get("policy_revision"):
            raise ChangeManagementControlError("approved command lacks authorization provenance")
        if command.get("approval_status") != "approved":
            raise ChangeManagementControlError("rollback_config requires an approved operational decision")
        parameters = command.get("parameters") if isinstance(command.get("parameters"), dict) else {}
        if not parameters.get("target_manifest_id"):
            raise ChangeManagementControlError("rollback_config requires target_manifest_id")
        return self._rollback_handler(deepcopy(command))
