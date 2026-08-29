"""Policy/Approval-gated external operational control gateway."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "Operations" / "RuntimeControl" / "action-catalog.yaml"
DEFAULT_APPROVAL_POLICY = ROOT / "Policy" / "Approval" / "approval-policy.yaml"
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}


class OperationalControlError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise OperationalControlError(f"expected mapping: {path}")
    return value


def _hashable_command(command: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in command.items() if key != "authorization_hash"}


def _authorization_hash(command: dict[str, Any]) -> str:
    payload = json.dumps(_hashable_command(command), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_request_scope(request: dict[str, Any]) -> None:
    action = str(request.get("action") or "")
    run_id = request.get("run_id")
    route_id = request.get("route_id")
    parameters = request.get("parameters") if isinstance(request.get("parameters"), dict) else {}
    if action in {"pause", "resume", "stop", "quarantine", "switch_model"} and not run_id:
        raise OperationalControlError(f"{action} requires run_id")
    if action == "switch_model" and not str(parameters.get("model") or ""):
        raise OperationalControlError("switch_model requires parameters.model")
    if action == "disable_route" and not (route_id or parameters.get("route_id")):
        raise OperationalControlError("disable_route requires route_id")
    if action == "rollback_config" and not str(parameters.get("target_manifest_id") or ""):
        raise OperationalControlError("rollback_config requires parameters.target_manifest_id")
    if action == "force_hitl" and not (run_id or route_id):
        raise OperationalControlError("force_hitl requires run_id or route_id")
    if action == "replay_checkpoint":
        if not str(parameters.get("checkpoint_id") or ""):
            raise OperationalControlError("replay_checkpoint requires parameters.checkpoint_id")
        if not str(parameters.get("resume_decision_ref") or ""):
            raise OperationalControlError("replay_checkpoint requires parameters.resume_decision_ref")


def _validate_policy_decision(action: str, minimum_risk: str, decision: dict[str, Any], approval_policy: dict[str, Any]) -> None:
    if decision.get("allowed") is not True:
        raise OperationalControlError("Policy denied operational control action")
    policy_revision = str(decision.get("policy_revision") or "")
    if not policy_revision:
        raise OperationalControlError("Policy decision requires policy_revision")
    risk_level = str(decision.get("risk_level") or "")
    if risk_level not in RISK_ORDER:
        raise OperationalControlError("Policy decision requires valid risk_level")
    if RISK_ORDER[risk_level] < RISK_ORDER[minimum_risk]:
        raise OperationalControlError(f"Policy risk {risk_level} is below action minimum {minimum_risk}")
    decided_action = decision.get("action")
    if decided_action is not None and str(decided_action) != action:
        raise OperationalControlError("Policy decision action does not match request")
    approval_required = decision.get("approval_required")
    if not isinstance(approval_required, bool):
        raise OperationalControlError("Policy decision requires approval_required boolean")
    requirement = str((approval_policy.get("requirements") or {}).get(risk_level) or "")
    if requirement == "always_required" and approval_required is not True:
        raise OperationalControlError("Policy decision conflicts with canonical always-required approval rule")
    if requirement == "not_required" and approval_required is not False:
        raise OperationalControlError("Policy decision conflicts with canonical no-approval rule")


def _validate_approval(decision: dict[str, Any], approval: dict[str, Any]) -> tuple[str, str | None]:
    required = decision["approval_required"]
    status = str(approval.get("status") or "")
    approval_id = str(approval.get("approval_id") or "") or None
    if required:
        if status != "approved" or approval_id is None:
            raise OperationalControlError("required approval is missing or not approved")
        return status, approval_id
    if status not in {"not_required", "approved"}:
        raise OperationalControlError("approval decision must be not_required or approved")
    if status == "approved" and approval_id is None:
        raise OperationalControlError("approved decision requires approval_id")
    if status == "not_required" and approval_id is not None:
        raise OperationalControlError("not_required approval must not carry approval_id")
    return status, approval_id


def authorize_control(
    request: dict[str, Any],
    *,
    policy_decision: dict[str, Any],
    approval_decision: dict[str, Any],
    catalog_path: Path = DEFAULT_CATALOG,
    approval_policy_path: Path = DEFAULT_APPROVAL_POLICY,
    authorized_at: str | None = None,
) -> dict[str, Any]:
    if request.get("schema_version") != "1.0":
        raise OperationalControlError("unsupported control request schema_version")
    action = str(request.get("action") or "")
    request_id = str(request.get("request_id") or "")
    if not action or not request_id:
        raise OperationalControlError("control request requires action and request_id")
    if not str(request.get("requested_by") or "") or not str(request.get("reason") or ""):
        raise OperationalControlError("control request requires requested_by and reason")
    _validate_request_scope(request)
    catalog = _load_yaml(catalog_path)
    action_spec = (catalog.get("actions") or {}).get(action)
    if not isinstance(action_spec, dict):
        raise OperationalControlError(f"unsupported operational action: {action}")
    approval_policy = _load_yaml(approval_policy_path)
    minimum_risk = str(action_spec.get("minimum_risk") or "")
    _validate_policy_decision(action, minimum_risk, policy_decision, approval_policy)
    approval_status, approval_id = _validate_approval(policy_decision, approval_decision)

    command = {
        "schema_version": "1.0",
        "command_id": f"cmd-{request_id}",
        "request_id": request_id,
        "action": action,
        "target_authority": str(action_spec["target_authority"]),
        "target_api": str(action_spec["target_api"]),
        "run_id": request.get("run_id"),
        "route_id": request.get("route_id"),
        "parameters": dict(request.get("parameters") or {}),
        "policy_revision": str(policy_decision["policy_revision"]),
        "risk_level": str(policy_decision["risk_level"]),
        "approval_status": approval_status,
        "approval_id": approval_id,
        "authorized_at": authorized_at or _now(),
    }
    command["authorization_hash"] = _authorization_hash(command)
    return command


def validate_approved_command(command: dict[str, Any], *, catalog_path: Path = DEFAULT_CATALOG) -> None:
    if command.get("schema_version") != "1.0" or not command.get("command_id"):
        raise OperationalControlError("raw or malformed control request cannot be dispatched")
    expected_hash = _authorization_hash(command)
    if command.get("authorization_hash") != expected_hash:
        raise OperationalControlError("control authorization hash mismatch")
    catalog = _load_yaml(catalog_path)
    action_spec = (catalog.get("actions") or {}).get(command.get("action"))
    if not isinstance(action_spec, dict):
        raise OperationalControlError("command action is not in canonical action catalog")
    if command.get("target_authority") != action_spec.get("target_authority"):
        raise OperationalControlError("command target authority drifted after authorization")
    if command.get("target_api") != action_spec.get("target_api"):
        raise OperationalControlError("command target API drifted after authorization")
    if command.get("approval_status") not in {"not_required", "approved"}:
        raise OperationalControlError("command does not carry a valid approval outcome")
    if not command.get("policy_revision"):
        raise OperationalControlError("command does not carry policy provenance")
    _validate_request_scope(command)


def dispatch_approved_control(
    command: dict[str, Any],
    *,
    ports: dict[str, Callable[[dict[str, Any]], Any]],
    catalog_path: Path = DEFAULT_CATALOG,
) -> Any:
    """Dispatch only to approved authority ports; never Runtime internals."""
    validate_approved_command(command, catalog_path=catalog_path)
    target = str(command["target_authority"])
    port = ports.get(target)
    if port is None:
        raise OperationalControlError(f"approved control port unavailable: {target}")
    return port(dict(command))


def build_control_audit(command: dict[str, Any], *, outcome: str, event_id: str, timestamp: str | None = None) -> dict[str, Any]:
    validate_approved_command(command)
    if outcome not in {"requested", "authorized", "rejected", "applied", "failed"}:
        raise OperationalControlError("invalid audit outcome")
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "run_id": command.get("run_id"),
        "actor_type": "operator",
        "action": str(command["action"]),
        "target": str(command["target_api"]),
        "outcome": outcome,
        "policy_revision": str(command["policy_revision"]),
        "approval_id": command.get("approval_id"),
        "timestamp": timestamp or _now(),
        "attributes": {"command_id": command["command_id"], "authorization_hash": command["authorization_hash"]},
        "evidence_refs": [],
    }
