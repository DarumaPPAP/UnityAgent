"""Normalize Installer Provider results into the existing Runtime Evidence bridge."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_toolchain_result(
    result: Mapping[str, Any],
    *,
    evidence_id: str,
    run_id: str,
    step_id: str,
    project_root: str,
    definition_fingerprint: Mapping[str, Any],
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Create a current-run evidence record for doctor/plan/apply results.

    Toolchain setup is a management operation rather than a Unity CapabilityRequest,
    so it uses the existing v1.0 Runtime-to-Persistence bridge. No separate evidence
    store or provider registry is introduced.
    """
    status = str(result.get("status") or "failed")
    if status not in {"passed", "failed", "unavailable", "unverified"}:
        raise ValueError(f"unsupported toolchain result status: {status}")
    operation = str(result.get("operation") or "")
    if operation not in {"doctor", "plan", "apply"}:
        raise ValueError("toolchain result operation must be doctor, plan or apply")
    payload = json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_hash = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return {
        "schema_version": "1.0",
        "evidence_id": evidence_id,
        "run_id": run_id,
        "step_id": step_id,
        "producer": "installer_provider",
        "source_type": "toolchain_result",
        "source_ref": f"toolchain:{operation}",
        "status": status,
        "payload_ref": result.get("plan_id") or result.get("receipt_id"),
        "hash": payload_hash,
        "timestamp": timestamp or _now(),
        "provenance": [
            "layer:provider",
            "provider:installer",
            f"operation:{operation}",
            f"project:{hashlib.sha256(project_root.encode('utf-8')).hexdigest()}",
        ],
        "gate_outcome": deepcopy(result.get("gate_outcome")),
        "definition_fingerprint": deepcopy(dict(definition_fingerprint)),
    }
