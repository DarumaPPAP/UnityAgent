"""Asynchronous operational failure detection over Runtime/Eval structured facts."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


DEFAULT_THRESHOLDS = {
    "retry_storm_count": 3,
    "latency_ms": 5000.0,
    "cost_usd": 2.0,
    "quality_pass_rate": 0.80,
    "quality_min_samples": 3,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(kind: str, run_ids: list[str], refs: list[str], attributes: dict[str, Any]) -> str:
    payload = json.dumps(
        {"kind": kind, "run_ids": sorted(run_ids), "refs": sorted(refs), "attributes": attributes},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "det-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _detection(
    kind: str,
    severity: str,
    run_ids: list[str],
    refs: list[str],
    attributes: dict[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    unique_runs = sorted(set(run_ids))
    unique_refs = sorted(set(refs))
    return {
        "schema_version": "1.0",
        "detection_id": _stable_id(kind, unique_runs, unique_refs, attributes),
        "kind": kind,
        "severity": severity,
        "status": "detected",
        "run_ids": unique_runs,
        "observed_at": observed_at,
        "signal_refs": unique_refs,
        "attributes": attributes,
    }


def detect_async_failures(
    *,
    trace_events: list[dict[str, Any]] | None = None,
    metric_events: list[dict[str, Any]] | None = None,
    eval_records: list[dict[str, Any]] | None = None,
    thresholds: dict[str, Any] | None = None,
    observed_at: str | None = None,
) -> list[dict[str, Any]]:
    """Detect operational failure signals without changing Runtime/Eval state."""
    traces = list(trace_events or [])
    metrics = list(metric_events or [])
    evals = list(eval_records or [])
    limits = dict(DEFAULT_THRESHOLDS)
    limits.update(thresholds or {})
    timestamp = observed_at or _now()
    detections: list[dict[str, Any]] = []

    retry_refs: dict[str, list[str]] = defaultdict(list)
    for event in traces:
        if event.get("event_type") not in {"runtime.retry", "tool.retry"}:
            continue
        run_id = str(event.get("run_id") or "")
        if not run_id:
            continue
        ref = str(event.get("span_id") or event.get("event_id") or "")
        if ref:
            retry_refs[run_id].append(ref)
    for run_id, refs in sorted(retry_refs.items()):
        if len(refs) >= int(limits["retry_storm_count"]):
            detections.append(_detection(
                "retry_storm", "error", [run_id], refs,
                {"retry_count": len(refs), "threshold": int(limits["retry_storm_count"])}, timestamp,
            ))

    for event in traces:
        if event.get("event_type") != "route.observed":
            continue
        attrs = event.get("attributes") if isinstance(event.get("attributes"), dict) else {}
        expected = str(attrs.get("expected_route") or "")
        actual = str(attrs.get("actual_route") or "")
        run_id = str(event.get("run_id") or "")
        if expected and actual and expected != actual and run_id:
            ref = str(event.get("span_id") or "")
            detections.append(_detection(
                "route_drift", "error", [run_id], [ref] if ref else [],
                {"expected_route": expected, "actual_route": actual}, timestamp,
            ))

    for metric in metrics:
        name = str(metric.get("metric_name") or "")
        run_id = str(metric.get("run_id") or "")
        ref = str(metric.get("event_id") or "")
        try:
            value = float(metric.get("value"))
        except (TypeError, ValueError):
            continue
        if not run_id:
            continue
        if name == "runtime.latency_ms" and value > float(limits["latency_ms"]):
            detections.append(_detection(
                "latency_drift", "warning", [run_id], [ref] if ref else [],
                {"value": value, "threshold": float(limits["latency_ms"]), "unit": "ms"}, timestamp,
            ))
        elif name == "runtime.cost_usd" and value > float(limits["cost_usd"]):
            detections.append(_detection(
                "cost_drift", "warning", [run_id], [ref] if ref else [],
                {"value": value, "threshold": float(limits["cost_usd"]), "unit": "usd"}, timestamp,
            ))
        elif name == "eval.regression_pass_rate" and value < float(limits["quality_pass_rate"]):
            detections.append(_detection(
                "quality_drift", "error", [run_id], [ref] if ref else [],
                {"pass_rate": value, "threshold": float(limits["quality_pass_rate"]), "source": "eval_metric"}, timestamp,
            ))

    eligible = [record for record in evals if record.get("quality_denominator_eligible") is True]
    if len(eligible) >= int(limits["quality_min_samples"]):
        passed = sum(1 for record in eligible if not record.get("failure_class"))
        pass_rate = passed / len(eligible)
        if pass_rate < float(limits["quality_pass_rate"]):
            run_ids = [str(record.get("run_id") or "") for record in eligible if record.get("run_id")]
            refs = [str(record.get("eval_id") or "") for record in eligible if record.get("eval_id")]
            detections.append(_detection(
                "quality_drift", "error", run_ids, refs,
                {"pass_rate": pass_rate, "sample_count": len(eligible), "threshold": float(limits["quality_pass_rate"]), "source": "eval_records"},
                timestamp,
            ))

    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for detection in detections:
        for run_id in detection["run_ids"]:
            by_run[run_id].append(detection)
    for run_id, items in sorted(by_run.items()):
        kinds = sorted({str(item["kind"]) for item in items})
        if len(kinds) < 2:
            continue
        refs = [str(item["detection_id"]) for item in items]
        severity_counts = Counter(str(item["severity"]) for item in items)
        severity = "critical" if severity_counts["error"] + severity_counts["critical"] >= 2 else "error"
        detections.append(_detection(
            "correlated_incident", severity, [run_id], refs,
            {"correlated_kinds": kinds, "signal_count": len(items)}, timestamp,
        ))

    unique: dict[str, dict[str, Any]] = {item["detection_id"]: item for item in detections}
    return [unique[key] for key in sorted(unique)]
