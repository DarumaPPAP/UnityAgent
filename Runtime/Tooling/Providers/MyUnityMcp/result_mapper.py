"""Structured MyUnityMCP ToolResult normalization.

Human-readable summaries are carried as diagnostics only; canonical facts are
derived from structured fields/status.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SUCCESS = "SUCCESS"
PARTIAL = "PARTIAL"
UNSUPPORTED = "UNSUPPORTED"
UNVERIFIED = "UNVERIFIED"
BACKEND_NOT_IMPLEMENTED = "BACKEND_NOT_IMPLEMENTED"


@dataclass(frozen=True)
class PreparedMutationProvenance:
    workflow_key: str
    prepare_tool: str
    apply_tool: str
    approval_group: str
    instance_id: str
    session_id: str
    plan_id: str
    expected_revision: int
    approval_token: str
    diff_digest: str
    mutation_scope_digest: str


@dataclass(frozen=True)
class AgentWorkflowProvenance:
    instance_id: str
    graph_id: str
    expected_revision: int
    required_approval_groups: tuple[str, ...]
    provider_approval_token: str | None = None


def _mapping(value: object) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def unwrap_structured_result(raw: object) -> dict[str, Any] | None:
    """Accept direct ToolResult/JObject projections, never human log text."""
    value = _mapping(raw)
    if value is None:
        return None

    for key in ("structuredContent", "structured_content", "result"):
        nested = _mapping(value.get(key))
        if nested is not None:
            value = nested
            break
    return value


def _reason(value: dict[str, Any]) -> str | None:
    for key in ("summary", "message", "reason"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    error = _mapping(value.get("error"))
    if error:
        for key in ("message", "summary"):
            item = error.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def normalize_tool_result(
    raw: object,
    *,
    evidence: tuple[str, ...] = (),
    provider_ref: str = "myunitymcp",
) -> dict[str, Any]:
    value = unwrap_structured_result(raw)
    if value is None:
        return {
            "status": "failed",
            "failure_class": "not_observed",
            "reason": "structured MyUnityMCP result was not observed",
            "provider_ref": provider_ref,
            "evidence": [],
        }

    if isinstance(value.get("success"), bool) and "status" not in value:
        if value["success"] is True:
            return {
                "status": "passed",
                "failure_class": None,
                "reason": None,
                "provider_ref": provider_ref,
                "structured_result": value,
                "evidence": list(evidence),
            }
        code = str(value.get("errorCode") or "")
        failure = "unsupported" if "UNSUPPORTED" in code else "execution_failed"
        if "REVISION" in code or "STALE" in code or "CATALOG-CHANGED" in code:
            failure = "precondition_failed"
        return {
            "status": "failed",
            "failure_class": failure,
            "reason": _reason(value) or code or "MyUnityMCP control-plane failure",
            "provider_ref": provider_ref,
            "structured_result": value,
            "evidence": [],
        }

    status = str(value.get("status") or "").upper()
    reason = _reason(value)

    if status == SUCCESS:
        return {
            "status": "passed",
            "failure_class": None,
            "reason": None,
            "provider_ref": provider_ref,
            "tool_status": status,
            "structured_result": value,
            "evidence": list(evidence),
        }

    if status == PARTIAL:
        failure = "execution_failed"
    elif status == UNSUPPORTED:
        failure = "unsupported"
    elif status == UNVERIFIED:
        failure = "not_observed"
    elif status == BACKEND_NOT_IMPLEMENTED:
        failure = "backend_not_implemented"
    elif status in {"SESSION_EXPIRED", "STALE_SNAPSHOT", "STALE_DURING_SCAN", "INVALID_REQUEST"}:
        failure = "precondition_failed"
    elif status == "EDITOR_RELOADING":
        failure = "unavailable"
    elif status == "READ_ONLY_CONTRACT_VIOLATION":
        failure = "execution_failed"
    elif status == "FAILED":
        failure = "execution_failed"
    else:
        failure = "not_observed"

    return {
        "status": "failed",
        "failure_class": failure,
        "reason": reason or (f"MyUnityMCP returned {status}" if status else "unknown MyUnityMCP status"),
        "provider_ref": provider_ref,
        "tool_status": status or None,
        "structured_result": value,
        "evidence": [],
    }


def extract_prepared_mutation(
    raw: object,
    *,
    workflow_key: str,
    prepare_tool: str,
    apply_tool: str,
    approval_group: str,
    instance_id: str,
    mutation_scope_digest: str,
) -> tuple[PreparedMutationProvenance | None, dict[str, Any]]:
    normalized = normalize_tool_result(raw, evidence=())
    if normalized["status"] != "passed":
        return None, normalized

    structured = normalized["structured_result"]
    data = _mapping(structured.get("data"))
    if data is None:
        return None, {
            **normalized,
            "status": "failed",
            "failure_class": "not_observed",
            "reason": "prepare result did not expose structured data",
            "evidence": [],
        }

    session_id = structured.get("sessionId")
    plan_id = data.get("planId")
    expected_revision = data.get("expectedRevision")
    approval_token = data.get("approvalToken")
    diff_digest = data.get("diffDigest")

    valid = (
        isinstance(session_id, str)
        and bool(session_id)
        and isinstance(plan_id, str)
        and bool(plan_id)
        and isinstance(expected_revision, int)
        and isinstance(approval_token, str)
        and bool(approval_token)
        and isinstance(diff_digest, str)
        and bool(diff_digest)
    )
    if not valid:
        return None, {
            **normalized,
            "status": "failed",
            "failure_class": "not_observed",
            "reason": "prepare result is missing plan/revision/approval/diff provenance",
            "evidence": [],
        }

    provenance = PreparedMutationProvenance(
        workflow_key=workflow_key,
        prepare_tool=prepare_tool,
        apply_tool=apply_tool,
        approval_group=approval_group,
        instance_id=instance_id,
        session_id=session_id,
        plan_id=plan_id,
        expected_revision=expected_revision,
        approval_token=approval_token,
        diff_digest=diff_digest,
        mutation_scope_digest=mutation_scope_digest,
    )
    return provenance, {
        **normalized,
        "prepared": True,
        "diff_digest": diff_digest,
        "evidence": [],
    }


def extract_agent_graph(
    raw: object,
    *,
    instance_id: str,
) -> tuple[AgentWorkflowProvenance | None, dict[str, Any]]:
    normalized = normalize_tool_result(raw)
    if normalized["status"] != "passed":
        return None, normalized
    value = normalized["structured_result"]

    graph_id = value.get("graphId")
    expected_revision = value.get("expectedRevision")
    groups = value.get("requiredApprovalGroups") or []
    if not isinstance(graph_id, str) or not graph_id or not isinstance(expected_revision, int):
        return None, {
            **normalized,
            "status": "failed",
            "failure_class": "not_observed",
            "reason": "compiled Agent graph provenance is incomplete",
            "evidence": [],
        }
    if not isinstance(groups, list) or not all(isinstance(item, str) for item in groups):
        return None, {
            **normalized,
            "status": "failed",
            "failure_class": "not_observed",
            "reason": "required approval groups are not structured",
            "evidence": [],
        }
    return AgentWorkflowProvenance(
        instance_id=instance_id,
        graph_id=graph_id,
        expected_revision=expected_revision,
        required_approval_groups=tuple(groups),
    ), normalized


def redacted_provenance(provenance: PreparedMutationProvenance) -> dict[str, Any]:
    """Projection safe for evidence/telemetry; never includes approval token."""
    return {
        "workflow_key": provenance.workflow_key,
        "prepare_tool": provenance.prepare_tool,
        "apply_tool": provenance.apply_tool,
        "approval_group": provenance.approval_group,
        "instance_id": provenance.instance_id,
        "session_id": provenance.session_id,
        "plan_id": provenance.plan_id,
        "expected_revision": provenance.expected_revision,
        "diff_digest": provenance.diff_digest,
        "mutation_scope_digest": provenance.mutation_scope_digest,
    }
