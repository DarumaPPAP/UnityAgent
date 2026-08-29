"""Append-oriented operational event backend with read-only query/search surfaces."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable


ACCEPTED_RECORD_TYPES = {
    "trace",
    "metric",
    "structured_log",
    "audit",
    "detection",
    "incident",
}


class OperationsBackendError(ValueError):
    pass


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _timestamp(record: dict[str, Any]) -> str:
    for key in ("timestamp", "observed_at", "created_at", "updated_at"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


class OperationalEventStore:
    """Operations-owned telemetry store; never an Execution/Evidence source of truth."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, record_type: str) -> Path:
        if record_type not in ACCEPTED_RECORD_TYPES:
            raise OperationsBackendError(f"unsupported record type: {record_type}")
        return self.root / f"{record_type}.jsonl"

    def append(self, record_type: str, record: dict[str, Any]) -> None:
        if not isinstance(record, dict) or record.get("schema_version") != "1.0":
            raise OperationsBackendError("operational record must be a schema_version=1.0 mapping")
        path = self._path(record_type)
        payload = (_canonical_json(record) + "\n").encode("utf-8")
        with path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def _records(self, record_types: Iterable[str]) -> Iterable[tuple[str, dict[str, Any]]]:
        for record_type in record_types:
            path = self._path(record_type)
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    yield record_type, value

    def query(
        self,
        *,
        record_type: str | None = None,
        run_id: str | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        metric_name: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            raise OperationsBackendError("limit must be positive")
        record_types = [record_type] if record_type else sorted(ACCEPTED_RECORD_TYPES)
        matches: list[dict[str, Any]] = []
        for kind, record in self._records(record_types):
            direct_run = record.get("run_id")
            run_ids = record.get("run_ids") if isinstance(record.get("run_ids"), list) else []
            if run_id and direct_run != run_id and run_id not in run_ids:
                continue
            if event_type and record.get("event_type") != event_type:
                continue
            if severity and record.get("severity") != severity:
                continue
            if metric_name and record.get("metric_name") != metric_name:
                continue
            timestamp = _timestamp(record)
            if since and (not timestamp or timestamp < since):
                continue
            if until and (not timestamp or timestamp > until):
                continue
            item = dict(record)
            item["_operations_record_type"] = kind
            matches.append(item)
        matches.sort(key=_timestamp)
        return matches[-limit:]

    def search_text(self, text: str, *, limit: int = 100) -> list[dict[str, Any]]:
        needle = str(text).strip().casefold()
        if not needle:
            return []
        results: list[dict[str, Any]] = []
        for kind, record in self._records(sorted(ACCEPTED_RECORD_TYPES)):
            if needle not in _canonical_json(record).casefold():
                continue
            item = dict(record)
            item["_operations_record_type"] = kind
            results.append(item)
            if len(results) >= limit:
                break
        return results
