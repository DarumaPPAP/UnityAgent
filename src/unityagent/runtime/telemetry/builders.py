"""Runtime telemetry builders compatible with Operations observability contracts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
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


def runtime_event(
    *,
    run_id: str,
    step_id: str | None,
    event: str,
    severity: str = "info",
    attributes: dict | None = None,
    evidence_refs: list[str] | None = None,
) -> dict:
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


def provider_capability_metrics(evidence: Mapping[str, Any]) -> list[dict]:
    """Project canonical Tool Runtime Evidence into observability metrics.

    Telemetry is a projection, not Evidence truth. Only fixed structured fields
    are copied; raw logs, provider payloads, approval tokens and reasons are not.
    """
    if evidence.get("schema_version") != "1.1":
        raise ValueError("provider metrics require Tool Runtime Evidence v1.1")
    required = {
        "run_id",
        "step_id",
        "evidence_id",
        "provider_ref",
        "capability",
        "completion",
        "status",
        "failure_class",
        "observation_state",
        "environment",
        "latency_ms",
        "fallback_from",
    }
    missing = sorted(required - set(evidence))
    if missing:
        raise ValueError(f"Tool Runtime Evidence missing metric fields: {missing}")

    environment = evidence.get("environment")
    if not isinstance(environment, Mapping):
        raise ValueError("Tool Runtime Evidence environment must be structured")
    attributes = {
        "provider_ref": str(evidence["provider_ref"]),
        "capability": str(evidence["capability"]),
        "completion": str(evidence["completion"]),
        "failure_class": evidence.get("failure_class"),
        "observation_state": str(evidence["observation_state"]),
        "environment_profile": environment.get("profile_hint"),
    }
    evidence_refs = [str(evidence["evidence_id"])]
    run_id = str(evidence["run_id"])
    step_id = str(evidence["step_id"])

    available = 0.0 if evidence.get("completion") == "blocked_by_environment" else 1.0
    selected = 1.0
    fallback = 1.0 if evidence.get("fallback_from") else 0.0
    failed = 1.0 if evidence.get("status") in {"failed", "unavailable"} else 0.0

    metrics = [
        runtime_metric(
            run_id=run_id,
            step_id=step_id,
            metric_name="tool_runtime.provider.availability",
            value=available,
            unit="ratio",
            attributes=attributes,
            evidence_refs=evidence_refs,
        ),
        runtime_metric(
            run_id=run_id,
            step_id=step_id,
            metric_name="tool_runtime.provider.selection",
            value=selected,
            unit="count",
            attributes=attributes,
            evidence_refs=evidence_refs,
        ),
        runtime_metric(
            run_id=run_id,
            step_id=step_id,
            metric_name="tool_runtime.provider.fallback",
            value=fallback,
            unit="count",
            attributes=attributes,
            evidence_refs=evidence_refs,
        ),
        runtime_metric(
            run_id=run_id,
            step_id=step_id,
            metric_name="tool_runtime.provider.failure",
            value=failed,
            unit="count",
            attributes=attributes,
            evidence_refs=evidence_refs,
        ),
    ]
    latency = evidence.get("latency_ms")
    if latency is not None:
        latency_value = float(latency)
        if latency_value < 0:
            raise ValueError("Tool Runtime Evidence latency_ms must be non-negative")
        metrics.append(
            runtime_metric(
                run_id=run_id,
                step_id=step_id,
                metric_name="tool_runtime.provider.latency",
                value=latency_value,
                unit="ms",
                attributes=attributes,
                evidence_refs=evidence_refs,
            )
        )
    return metrics
