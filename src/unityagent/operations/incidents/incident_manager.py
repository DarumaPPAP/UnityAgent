"""Incident correlation and runbook selection for Operations."""
from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


_SEVERITY_ORDER = {"warning": 0, "error": 1, "critical": 2}
_ALLOWED_TRANSITIONS = {"open": {"mitigated", "resolved"}, "mitigated": {"resolved"}, "resolved": set()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runbook_for(detections: list[dict[str, Any]]) -> str:
    kinds = {str(item.get("kind") or "") for item in detections}
    if "correlated_incident" in kinds and any(item.get("severity") == "critical" for item in detections):
        return "critical-containment"
    if "retry_storm" in kinds:
        return "retry-storm"
    return "drift"


def build_incident(detections: list[dict[str, Any]], *, created_at: str | None = None) -> dict[str, Any]:
    if not detections:
        raise ValueError("incident requires at least one detection")
    run_ids = sorted({str(run_id) for item in detections for run_id in item.get("run_ids", []) if run_id})
    if not run_ids:
        raise ValueError("incident detections must reference at least one run")
    detection_refs = sorted({str(item.get("detection_id") or "") for item in detections if item.get("detection_id")})
    if len(detection_refs) != len(detections):
        raise ValueError("all detections require detection_id")
    severity = max(
        (str(item.get("severity") or "warning") for item in detections),
        key=lambda value: _SEVERITY_ORDER.get(value, -1),
    )
    stamp = created_at or _now()
    digest_source = "|".join(detection_refs)
    incident_id = "inc-" + hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:20]
    kinds = sorted({str(item.get("kind") or "unknown") for item in detections})
    return {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "severity": severity,
        "status": "open",
        "summary": f"Operational detection correlation: {', '.join(kinds)}",
        "detection_refs": detection_refs,
        "run_ids": run_ids,
        "runbook_id": _runbook_for(detections),
        "created_at": stamp,
        "updated_at": stamp,
    }


def transition_incident(incident: dict[str, Any], new_status: str, *, updated_at: str | None = None) -> dict[str, Any]:
    current = str(incident.get("status") or "")
    if new_status not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid incident transition: {current} -> {new_status}")
    updated = deepcopy(incident)
    updated["status"] = new_status
    updated["updated_at"] = updated_at or _now()
    return updated
