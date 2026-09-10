"""Normalize UnityArtistCLI envelopes into the canonical ProviderResult shape."""
from __future__ import annotations

from typing import Any, Mapping

COMMAND_EVIDENCE: dict[str, tuple[str, ...]] = {
    "inspect": ("domain_result",),
    "plan": ("domain_result",),
    "preview": ("domain_result",),
    "apply": ("domain_result", "mutation_evidence"),
    "capture": ("visual_capture",),
    "evaluate": ("domain_result",),
    "refine": ("domain_result", "mutation_evidence"),
    "history": ("domain_result",),
    "cinematic": ("domain_result", "mutation_evidence"),
}

DECLARED_EVIDENCE = frozenset(
    {
        "domain_result",
        "mutation_evidence",
        "visual_capture",
        "visual_art_inspection",
        "pipeline_support_fact",
        "visual_direction_plan",
        "exact_diff",
        "expected_revision",
        "camera_binding",
        "capture_manifest",
        "cinematic_plan",
        "timeline_evidence",
        "artist_validation",
        "human_review_decision",
        "refinement_plan",
        "evaluation_reference",
        "undo_registration",
        "save_not_performed",
    }
)


def _value(envelope: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in envelope:
            return envelope[name]
    return None


def _failure_class(code: str | None) -> str:
    if code in {"APPROVAL_REQUIRED", "EXPECTED_REVISION_REQUIRED"}:
        return "blocked_by_approval"
    if code in {"STALE_REVISION", "PLAN_ID_REQUIRED", "CAPTURE_ID_REQUIRED", "EVALUATION_ID_REQUIRED"}:
        return "precondition_failed"
    if code in {"UNSUPPORTED_RENDER_PIPELINE_VERSION", "UNSUPPORTED_UNITY_VERSION", "UNKNOWN_RENDER_PIPELINE", "CAPABILITY_UNAVAILABLE"}:
        return "unsupported"
    if code in {"UNITY_CLI_UNAVAILABLE", "PIPELINE_UNAVAILABLE", "PIPELINE_NOT_REACHABLE"}:
        return "unavailable"
    if code in {"TIMEOUT", "PIPELINE_TIMEOUT"}:
        return "timeout"
    return "execution_failed"


def _payload_evidence(data: Any) -> list[str]:
    """Keep only declared semantic evidence from a Pipeline result.

    The Editor adapter may attach diagnostic values such as ``camera_binding:Main``.
    The canonical Runtime contract stores the semantic token and leaves the detailed
    value inside the structured result reference.
    """
    candidates: list[Any] = []
    if isinstance(data, Mapping):
        candidates.extend(data.get("evidence") or [])
        nested = data.get("provider")
        if isinstance(nested, Mapping):
            candidates.extend(nested.get("evidence") or [])
        nested = data.get("adapter")
        if isinstance(nested, Mapping):
            candidates.extend(nested.get("evidence") or [])
    result: list[str] = []
    for item in candidates:
        token = str(item).split(":", 1)[0].strip()
        if token in DECLARED_EVIDENCE and token not in result:
            result.append(token)
    return result


def normalize_artist_result(
    payload: Any,
    *,
    command: str,
    provider_ref: str = "unity_artist_cli",
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {
            "status": "failed",
            "failure_class": "not_observed",
            "reason": "UnityArtistCLI returned a non-object JSON payload",
            "provider_ref": provider_ref,
            "evidence": [],
        }

    status = str(_value(payload, "Status", "status") or "")
    data = _value(payload, "Data", "data")
    errors = _value(payload, "Errors", "errors")
    warnings = _value(payload, "Warnings", "warnings")
    evidence = list(COMMAND_EVIDENCE.get(command, ("domain_result",)))
    for item in _payload_evidence(data):
        if item not in evidence:
            evidence.append(item)
    if status == "passed":
        result: dict[str, Any] = {
            "status": "passed",
            "failure_class": None,
            "reason": None,
            "provider_ref": provider_ref,
            "evidence": evidence,
            "payload": data,
            "warnings": [str(item) for item in warnings or []],
            "command_id": f"artist.{command}",
        }
        if "mutation_evidence" in evidence:
            result["redacted_provenance"] = {
                "plan_id": _value(data, "planId", "plan_id") if isinstance(data, Mapping) else None,
                "session_id": _value(data, "sessionId", "session_id") if isinstance(data, Mapping) else None,
                "expected_revision": _value(data, "expectedRevision", "expected_revision") if isinstance(data, Mapping) else None,
                "exact_diff_ref": _value(data, "diffDigest", "diff_digest") if isinstance(data, Mapping) else None,
            }
        return result

    first_error = errors[0] if isinstance(errors, list) and errors else {}
    code = None
    message = "UnityArtistCLI returned a blocked or failed result"
    if isinstance(first_error, Mapping):
        raw_code = _value(first_error, "Code", "code")
        code = str(raw_code) if raw_code else None
        raw_message = _value(first_error, "Message", "message")
        if raw_message:
            message = str(raw_message)
    return {
        "status": "failed",
        "failure_class": _failure_class(code),
        "reason": message,
        "provider_ref": provider_ref,
        "evidence": [],
        "payload": data,
        "command_id": f"artist.{command}",
        "error_code": code,
    }
