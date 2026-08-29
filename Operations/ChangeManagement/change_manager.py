"""Version manifest and approval-gated change-management helpers."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from Persistence.Contracts.definition_fingerprint import DEFINITION_FIELDS, validate_definition_fingerprint


class ChangeManagementError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_version_manifest(
    definition_fingerprint: dict[str, Any],
    *,
    manifest_id: str,
    operations_revision: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_definition_fingerprint(definition_fingerprint)
    if not manifest_id or not operations_revision:
        raise ChangeManagementError("manifest_id and operations_revision are required")
    manifest = {
        "schema_version": "1.0",
        "manifest_id": manifest_id,
        **{field: str(definition_fingerprint[field]) for field in DEFINITION_FIELDS},
        "operations_revision": operations_revision,
        "generated_at": generated_at or _now(),
    }
    return manifest


def build_change_request(
    *,
    change_id: str,
    kind: str,
    current_manifest_id: str,
    target_manifest_id: str,
    summary: str,
    source_change_proposal_refs: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if kind not in {"rollout", "rollback", "config_update"}:
        raise ChangeManagementError(f"unsupported change kind: {kind}")
    if not all((change_id, current_manifest_id, target_manifest_id, summary.strip())):
        raise ChangeManagementError("change request identifiers and summary are required")
    if current_manifest_id == target_manifest_id:
        raise ChangeManagementError("change target must differ from current manifest")
    return {
        "schema_version": "1.0",
        "change_id": change_id,
        "kind": kind,
        "status": "proposed",
        "current_manifest_id": current_manifest_id,
        "target_manifest_id": target_manifest_id,
        "summary": summary,
        "source_change_proposal_refs": sorted(set(source_change_proposal_refs or [])),
        "policy_decision_ref": None,
        "approval_decision_ref": None,
        "created_at": created_at or _now(),
    }


def authorize_change(
    request: dict[str, Any],
    *,
    policy_decision: dict[str, Any],
    approval_decision: dict[str, Any],
) -> dict[str, Any]:
    if request.get("status") != "proposed":
        raise ChangeManagementError("only proposed changes can be authorized")
    if policy_decision.get("allowed") is not True:
        raise ChangeManagementError("Policy denied change request")
    policy_ref = str(policy_decision.get("decision_ref") or "")
    if not policy_ref:
        raise ChangeManagementError("Policy decision_ref is required")
    approval_required = policy_decision.get("approval_required")
    if not isinstance(approval_required, bool):
        raise ChangeManagementError("Policy approval_required decision is required")
    approval_status = str(approval_decision.get("status") or "")
    approval_ref = str(approval_decision.get("decision_ref") or "")
    if approval_required and approval_status != "approved":
        raise ChangeManagementError("required change approval is missing")
    if approval_status not in {"approved", "not_required"}:
        raise ChangeManagementError("invalid approval decision")
    if not approval_ref:
        raise ChangeManagementError("Approval decision_ref is required even when approval is not required")
    authorized = deepcopy(request)
    authorized["status"] = "authorized"
    authorized["policy_decision_ref"] = policy_ref
    authorized["approval_decision_ref"] = approval_ref
    return authorized


def apply_authorized_change(
    request: dict[str, Any],
    *,
    apply_port: Callable[[dict[str, Any]], Any],
) -> tuple[dict[str, Any], Any]:
    """Apply only through an injected ChangeManagement deployment port."""
    if request.get("status") != "authorized":
        raise ChangeManagementError("unauthorized change cannot be applied")
    if not request.get("policy_decision_ref") or not request.get("approval_decision_ref"):
        raise ChangeManagementError("authorized change is missing Policy/Approval provenance")
    result = apply_port(deepcopy(request))
    applied = deepcopy(request)
    applied["status"] = "applied"
    return applied, result
