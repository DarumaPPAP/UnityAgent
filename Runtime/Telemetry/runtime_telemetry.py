"""Runtime telemetry builders compatible with Operations observability contracts."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_span(
    *,
    run_id: str,
    step_id: str | None,
    event: str,
    severity: str = "info",
    attributes: dict | None = None,
    evidence_refs: list[str] | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    timestamp: str | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "trace_id": trace_id or run_id,
        "span_id": span_id or uuid.uuid4().hex[:16],
        "parent_span_id": parent_span_id,
        "run_id": run_id,
        "step_id": step_id,
        "event_type": event,
        "severity": severity,
        "timestamp": timestamp or _now(),
        "attributes": dict(attributes or {}),
        "evidence_refs": list(evidence_refs or []),
    }


def runtime_event(*, run_id: str, step_id: str | None, event: str, severity: str = "info", attributes: dict | None = None, evidence_refs: list[str] | None = None) -> dict:
    """Backward-compatible TraceRecord builder."""
    return runtime_span(
        run_id=run_id,
        step_id=step_id,
        event=event,
        severity=severity,
        attributes=attributes,
        evidence_refs=evidence_refs,
    )


def runtime_metric(
    *,
    run_id: str,
    step_id: str | None,
    metric_name: str,
    value: float,
    unit: str,
    attributes: dict | None = None,
    evidence_refs: list[str] | None = None,
    event_id: str | None = None,
    timestamp: str | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "event_id": event_id or f"metric-{uuid.uuid4().hex}",
        "run_id": run_id,
        "step_id": step_id,
        "metric_name": metric_name,
        "value": float(value),
        "unit": unit,
        "timestamp": timestamp or _now(),
        "attributes": dict(attributes or {}),
        "evidence_refs": list(evidence_refs or []),
    }


def runtime_log(
    *,
    run_id: str,
    step_id: str | None,
    logger: str,
    message: str,
    severity: str = "info",
    fields: dict | None = None,
    evidence_refs: list[str] | None = None,
    event_id: str | None = None,
    timestamp: str | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "event_id": event_id or f"log-{uuid.uuid4().hex}",
        "run_id": run_id,
        "step_id": step_id,
        "severity": severity,
        "logger": logger,
        "message": message,
        "timestamp": timestamp or _now(),
        "fields": dict(fields or {}),
        "evidence_refs": list(evidence_refs or []),
    }


def runtime_audit(
    *,
    run_id: str | None,
    action: str,
    target: str,
    outcome: str,
    policy_revision: str,
    approval_id: str | None,
    attributes: dict | None = None,
    evidence_refs: list[str] | None = None,
    event_id: str | None = None,
    timestamp: str | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "event_id": event_id or f"audit-{uuid.uuid4().hex}",
        "run_id": run_id,
        "actor_type": "runtime",
        "action": action,
        "target": target,
        "outcome": outcome,
        "policy_revision": policy_revision,
        "approval_id": approval_id,
        "timestamp": timestamp or _now(),
        "attributes": dict(attributes or {}),
        "evidence_refs": list(evidence_refs or []),
    }
