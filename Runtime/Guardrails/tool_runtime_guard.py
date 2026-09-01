"""Last-mile Runtime guard for tool dispatch and infrastructure fallback.

This adapter revalidates the canonical CapabilityRequest against the current
Environment Snapshot and Policy/Approval context immediately before execution.
It does not select a provider or make semantic routing decisions.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from Policy.Security.capability_policy import policy_for_capability
from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.capability_resolver import ResolutionContext

HARD_APPROVAL_REQUIREMENTS = frozenset(
    {
        "required_for_project_asset_or_settings_change",
        "always_required",
    }
)


@dataclass(frozen=True)
class RuntimeGuardResult:
    allowed: bool
    failure_class: str | None
    reason: str | None


def mutation_scope_fingerprint(request: dict[str, Any]) -> str | None:
    scope = request.get("mutation_scope")
    if scope is None:
        return None
    if not isinstance(scope, dict):
        return "<invalid>"
    normalized = {
        "allowed_paths": sorted(str(item) for item in scope.get("allowed_paths") or []),
        "prohibited_paths": sorted(
            str(item) for item in scope.get("prohibited_paths") or []
        ),
    }
    material = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def guard_runtime_dispatch(
    request: dict[str, Any],
    environment_snapshot: dict[str, Any],
    *,
    context: ResolutionContext,
    original_request: dict[str, Any] | None = None,
) -> RuntimeGuardResult:
    try:
        validate_capability_request(request)
        validate_environment_snapshot(environment_snapshot)
        if original_request is not None:
            validate_capability_request(original_request)
    except Exception as exc:
        return RuntimeGuardResult(
            False,
            "precondition_failed",
            f"invalid Runtime dispatch contract: {exc}",
        )

    snapshot_project = environment_snapshot.get("project") or {}
    if snapshot_project.get("identity_status") != "bound":
        value = snapshot_project.get("identity_status")
        return RuntimeGuardResult(
            False,
            "unknown" if value == "unknown" else "unavailable",
            f"project identity is not bound ({value})",
        )
    if not same_project_root(
        str(request["project_root"]),
        str(snapshot_project.get("root") or ""),
    ):
        return RuntimeGuardResult(
            False,
            "scope_violation",
            "CapabilityRequest project_root does not match current Environment Snapshot",
        )

    if not context.policy_allowed:
        return RuntimeGuardResult(False, "blocked_by_policy", "Policy denied dispatch")

    policy = policy_for_capability(str(request["capability"]))
    approval_requirement = str(policy["approval_requirement"])
    approval_required = (
        approval_requirement in HARD_APPROVAL_REQUIREMENTS
        or context.approval_required is True
    )
    if approval_required:
        if not request.get("approval_ref"):
            return RuntimeGuardResult(
                False,
                "blocked_by_approval",
                "required approval_ref is missing",
            )
        if context.approval_complete is not True:
            return RuntimeGuardResult(
                False,
                "blocked_by_approval",
                "required approval is not complete",
            )

    if policy["requires_mutation_scope"]:
        scope = request.get("mutation_scope")
        if not isinstance(scope, dict) or not scope.get("allowed_paths"):
            return RuntimeGuardResult(
                False,
                "scope_violation",
                "mutation scope is required immediately before dispatch",
            )

    if original_request is not None:
        if request["capability"] != original_request["capability"]:
            return RuntimeGuardResult(
                False,
                "precondition_failed",
                "infrastructure recovery changed capability semantics",
            )
        if not same_project_root(
            str(request["project_root"]),
            str(original_request["project_root"]),
        ):
            return RuntimeGuardResult(
                False,
                "scope_violation",
                "infrastructure recovery changed project root",
            )
        if set(request["required_evidence"]) != set(
            original_request["required_evidence"]
        ):
            return RuntimeGuardResult(
                False,
                "precondition_failed",
                "infrastructure recovery changed evidence requirements",
            )
        if mutation_scope_fingerprint(request) != mutation_scope_fingerprint(
            original_request
        ):
            return RuntimeGuardResult(
                False,
                "scope_violation",
                "infrastructure recovery changed or expanded Mutation Scope",
            )
        if request.get("approval_ref") != original_request.get("approval_ref"):
            return RuntimeGuardResult(
                False,
                "blocked_by_approval",
                "infrastructure recovery changed approval provenance",
            )

    return RuntimeGuardResult(True, None, None)
