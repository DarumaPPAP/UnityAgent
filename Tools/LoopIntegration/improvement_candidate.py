"""Create evidence-backed improvement candidates without writing Canonical files."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_improvement_candidate(run: dict[str, Any]) -> dict[str, Any]:
    source = {
        "run_id": run.get("run_id"),
        "failure_signature": run.get("failure_signature"),
        "target": run.get("target"),
    }
    candidate_id = "candidate-" + hashlib.sha256(
        json.dumps(source, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:24]
    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "trigger": run.get("trigger", "observed_failure"),
        "source_run": run.get("run_id"),
        "evidence_refs": list(run.get("evidence_refs", []) or []),
        "canonical_owner": run.get("canonical_owner"),
        "target": run.get("target"),
        "failure_signature": run.get("failure_signature"),
        "boundary_pair": run.get("boundary_pair"),
        "status": "proposed",
    }


def validate_improvement_candidate(candidate: dict[str, Any]) -> list[str]:
    required = (
        "candidate_id", "trigger", "source_run", "evidence_refs", "canonical_owner",
        "target", "failure_signature", "boundary_pair", "status",
    )
    errors = [f"missing field: {field}" for field in required if field not in candidate]
    if candidate.get("status") == "accepted" and not candidate.get("human_review_ref"):
        errors.append("accepted candidate requires human_review_ref")
    if not candidate.get("evidence_refs"):
        errors.append("candidate requires evidence_refs")
    return errors
