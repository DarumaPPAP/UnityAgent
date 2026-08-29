"""Runtime telemetry event builder compatible with Operations TraceRecord semantics."""
from __future__ import annotations
from datetime import datetime, timezone
import uuid


def runtime_event(*, run_id: str, step_id: str | None, event: str, severity: str = "info", attributes: dict | None = None, evidence_refs: list[str] | None = None) -> dict:
    return {"schema_version": "1.0", "trace_id": run_id, "span_id": uuid.uuid4().hex[:16], "run_id": run_id, "step_id": step_id, "event_type": event, "severity": severity, "timestamp": datetime.now(timezone.utc).isoformat(), "attributes": dict(attributes or {}), "evidence_refs": list(evidence_refs or [])}
