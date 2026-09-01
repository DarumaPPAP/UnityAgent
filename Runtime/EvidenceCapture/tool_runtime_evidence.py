"""Canonical current-run evidence normalization for Tool Runtime provider results.

This module owns only current-run Runtime evidence. Durable Evidence truth begins
only after Persistence/Evidence accepts the normalized record.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Guardrails.tool_runtime_guard import mutation_scope_fingerprint
from Runtime.Tooling.Environment.environment_snapshot import validate_environment_snapshot
from Runtime.Tooling.Environment.project_identity import same_project_root
from Runtime.Tooling.provider_registry import RuntimeProviderRegistry

_COMPLETIONS = frozenset(
    {
        "verified",
        "partial_verified",
        "implemented_unverified",
        "blocked_by_environment",
        "not_applicable",
    }
)
_FAILURE_CLASSES = frozenset(
    {
        "unavailable",
        "unknown",
        "unhealthy",
        "ambiguous_binding",
        "blocked_by_policy",
        "blocked_by_approval",
        "scope_violation",
        "unsupported",
        "backend_not_implemented",
        "precondition_failed",
        "execution_failed",
        "cancelled",
        "timeout",
        "observed_test_failure",
        "not_observed",
    }
)
_ENVIRONMENT_FAILURES = frozenset(
    {
        "unavailable",
        "unknown",
        "unhealthy",
        "ambiguous_binding",
        "unsupported",
        "backend_not_implemented",
        "timeout",
    }
)
_SENSITIVE_KEY_PARTS = ("secret", "password", "token", "credential", "keystore", "serial")
_SENSITIVE_REF_RE = re.compile(
    r"(?i)(?P<key>token|secret|password|credential|client_secret|access_token)="
    r"(?P<value>[^&\s]+)"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(value: Any) -> str:
    material = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(material).hexdigest()


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if any(part in text_key.casefold() for part in _SENSITIVE_KEY_PARTS):
                result[text_key] = "***"
            else:
                result[text_key] = _redact_sensitive(item)
        return result
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return _SENSITIVE_REF_RE.sub(lambda m: f"{m.group('key')}=***", value)
    return value


def _string_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a string array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain non-empty strings")
        result.append(item.strip())
    return list(dict.fromkeys(result))


def _completion(
    *,
    provider_status: str,
    failure_class: str | None,
    observed_evidence: set[str],
    required_evidence: set[str],
) -> tuple[str, str]:
    if provider_status == "not_applicable":
        return "not_applicable", "not_observed"

    required_satisfied = required_evidence.issubset(observed_evidence)
    if provider_status == "passed":
        if required_satisfied:
            return "verified", "observed"
        if observed_evidence:
            return "partial_verified", "observed"
        return "implemented_unverified", "not_observed"

    if failure_class in {"observed_test_failure", "execution_failed"} and observed_evidence:
        if required_satisfied:
            return "verified", "observed"
        return "partial_verified", "observed"

    if observed_evidence:
        return "partial_verified", "observed"
    if failure_class in _ENVIRONMENT_FAILURES:
        return "blocked_by_environment", "not_observed"
    return "implemented_unverified", "not_observed"


def _evidence_status(
    *,
    provider_status: str,
    completion: str,
    failure_class: str | None,
) -> str:
    if provider_status == "not_applicable":
        return "unverified"
    if provider_status == "passed":
        return "passed" if completion in {"verified", "partial_verified"} else "unverified"
    if failure_class in _ENVIRONMENT_FAILURES:
        return "unavailable"
    if failure_class == "not_observed":
        return "unverified"
    return "failed"


def _environment_projection(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    project = snapshot.get("project") if isinstance(snapshot.get("project"), Mapping) else {}
    build = snapshot.get("build") if isinstance(snapshot.get("build"), Mapping) else {}
    return {
        "profile_hint": snapshot.get("profile_hint"),
        "binding_fingerprint": str(snapshot.get("binding_fingerprint") or ""),
        "unity_version": project.get("unity_version"),
        "requested_target": build.get("requested_target"),
    }


def _target_projection(
    *,
    resolution: Mapping[str, Any],
    environment_snapshot: Mapping[str, Any],
    provider_result: Mapping[str, Any],
    explicit_target: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if explicit_target is not None:
        candidate = {
            "surface": explicit_target.get("surface"),
            "instance_id": explicit_target.get("instance_id"),
            "device_id": explicit_target.get("device_id"),
            "artifact_id": explicit_target.get("artifact_id"),
            "command_ref": explicit_target.get("command_ref"),
        }
    else:
        provider_ref = str(resolution.get("provider_ref") or "")
        provider_env = environment_snapshot.get(provider_ref)
        instance_id = provider_result.get("instance_id")
        if instance_id is None and isinstance(provider_env, Mapping):
            instance_id = provider_env.get("bound_instance_id")
        if provider_ref == "player_runtime" and instance_id is None:
            player = environment_snapshot.get("player_runtime")
            if isinstance(player, Mapping):
                instance_id = player.get("instance_id")
        candidate = {
            "surface": resolution.get("observed_surface"),
            "instance_id": instance_id,
            "device_id": provider_result.get("target_device_id"),
            "artifact_id": provider_result.get("artifact_id"),
            "command_ref": (
                provider_result.get("command_id")
                or provider_result.get("tool_name")
                or provider_result.get("path")
            ),
        }
    surface = candidate.get("surface")
    if surface not in {"project", "host", "editor", "live_editor", "player", None}:
        raise ValueError(f"unsupported target surface: {surface}")
    return {
        key: (None if value is None else str(value))
        for key, value in candidate.items()
    }


def _mutation_provenance(
    *,
    request: Mapping[str, Any],
    provider_result: Mapping[str, Any],
    explicit: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    capability = str(request.get("capability") or "")
    operation_kind = str(request.get("operation_kind") or "")
    if capability not in {"source.patch", "scene.mutate", "player.mutate"} and operation_kind not in {
        "source_mutation",
        "editor_mutation",
        "player_mutate",
        "save",
        "bake",
    }:
        return None

    provider_provenance = provider_result.get("redacted_provenance")
    if not isinstance(provider_provenance, Mapping):
        provider_provenance = {}
    supplied = explicit if isinstance(explicit, Mapping) else {}
    merged = {**provider_provenance, **supplied}
    safe = _redact_sensitive(merged)

    expected_revision = safe.get("expected_revision")
    if expected_revision is None:
        expected_revision = safe.get("expectedRevision")
    if expected_revision is not None:
        try:
            expected_revision = int(expected_revision)
        except (TypeError, ValueError) as exc:
            raise ValueError("mutation expected_revision must be an integer") from exc

    exact_diff_ref = safe.get("exact_diff_ref")
    diff_digest = safe.get("diff_digest") or safe.get("diffDigest")
    before_fp = (
        safe.get("before_fingerprint")
        or provider_result.get("before_sha256")
    )
    after_fp = (
        safe.get("after_fingerprint")
        or provider_result.get("after_sha256")
    )
    return {
        "approval_ref": request.get("approval_ref"),
        "expected_revision": expected_revision,
        "exact_diff_ref": None if exact_diff_ref is None else str(exact_diff_ref),
        "diff_digest": None if diff_digest is None else str(diff_digest),
        "scope_fingerprint": mutation_scope_fingerprint(dict(request)),
        "plan_ref": (
            None
            if safe.get("plan_id", safe.get("planId")) is None
            else str(safe.get("plan_id", safe.get("planId")))
        ),
        "session_ref": (
            None
            if safe.get("session_id", safe.get("sessionId")) is None
            else str(safe.get("session_id", safe.get("sessionId")))
        ),
        "approval_group": (
            None if safe.get("approval_group") is None else str(safe.get("approval_group"))
        ),
        "before_fingerprint": None if before_fp is None else str(before_fp),
        "after_fingerprint": None if after_fp is None else str(after_fp),
    }


def normalize_provider_result(
    request: dict[str, Any],
    resolution: Mapping[str, Any],
    environment_snapshot: dict[str, Any],
    provider_result: Mapping[str, Any],
    *,
    run_id: str,
    step_id: str,
    evidence_id: str,
    definition_fingerprint: Mapping[str, Any],
    raw_refs: Sequence[str] = (),
    structured_result_ref: str | None = None,
    target: Mapping[str, Any] | None = None,
    mutation_provenance: Mapping[str, Any] | None = None,
    latency_ms: float | None = None,
    fallback_from: str | None = None,
    provenance_refs: Sequence[str] = (),
    timestamp: str | None = None,
    registry: RuntimeProviderRegistry | None = None,
) -> dict[str, Any]:
    """Normalize one structured ProviderResult into canonical current-run Evidence.

    Provider human log text is intentionally ignored. Callers may retain raw
    log/artifact locations only through raw_refs.
    """
    validate_capability_request(request)
    validate_environment_snapshot(environment_snapshot)
    if not run_id or not step_id or not evidence_id:
        raise ValueError("run_id, step_id and evidence_id are required")
    if not isinstance(provider_result, Mapping):
        raise ValueError("provider_result must be a structured mapping")

    capability = str(request["capability"])
    if resolution.get("status") != "resolved":
        raise ValueError("capability resolution must be resolved before evidence normalization")
    if resolution.get("capability") != capability:
        raise ValueError("resolution capability does not match CapabilityRequest")
    provider_ref = str(resolution.get("provider_ref") or "")
    if not provider_ref:
        raise ValueError("resolved provider_ref is required")
    result_provider = provider_result.get("provider_ref")
    if result_provider is not None and str(result_provider) != provider_ref:
        raise ValueError("ProviderResult provider_ref does not match resolution")

    snapshot_project = environment_snapshot.get("project")
    if not isinstance(snapshot_project, Mapping):
        raise ValueError("Environment Snapshot project fact is missing")
    snapshot_root = str(snapshot_project.get("root") or "")
    if not same_project_root(str(request["project_root"]), snapshot_root):
        raise ValueError("Provider evidence Project Root does not match Environment Snapshot")

    runtime_registry = registry or RuntimeProviderRegistry()
    provider = runtime_registry.provider(provider_ref)
    if capability not in provider.capabilities:
        raise ValueError(f"{provider_ref} does not declare capability {capability}")
    requirement = runtime_registry.registry.capability_requirements[capability]
    if provider.safety_strength < requirement.minimum_safety_strength:
        raise ValueError("provider safety strength is below capability requirement")
    if provider.evidence_strength < requirement.minimum_evidence_strength:
        raise ValueError("provider evidence strength is below capability requirement")

    provider_status = str(provider_result.get("status") or "")
    if provider_status not in {"passed", "failed", "not_applicable"}:
        raise ValueError(f"unsupported ProviderResult status: {provider_status!r}")
    failure_class = provider_result.get("failure_class")
    if failure_class is not None:
        failure_class = str(failure_class)
        if failure_class not in _FAILURE_CLASSES:
            raise ValueError(f"unsupported ProviderResult failure_class: {failure_class}")
    if provider_status == "failed" and failure_class is None:
        raise ValueError("failed ProviderResult requires failure_class")
    if provider_status != "failed" and failure_class is not None:
        raise ValueError("non-failed ProviderResult cannot carry failure_class")

    observed = set(_string_list(provider_result.get("evidence"), field="ProviderResult.evidence"))
    offer = provider.capabilities[capability]
    unsupported_evidence = observed - set(offer.evidence_supported)
    if unsupported_evidence:
        raise ValueError(
            f"{provider_ref} emitted undeclared evidence for {capability}: "
            f"{sorted(unsupported_evidence)}"
        )
    required = set(_string_list(request.get("required_evidence"), field="required_evidence"))
    completion, observation_state = _completion(
        provider_status=provider_status,
        failure_class=failure_class,
        observed_evidence=observed,
        required_evidence=required,
    )
    if completion not in _COMPLETIONS:
        raise AssertionError("invalid completion state")

    safe_raw_refs = [
        str(_redact_sensitive(item))
        for item in _string_list(list(raw_refs), field="raw_refs")
    ]
    safe_provenance_refs = [
        str(_redact_sensitive(item))
        for item in _string_list(list(provenance_refs), field="provenance_refs")
    ]
    binding_fingerprint = str(environment_snapshot.get("binding_fingerprint") or "")
    provenance = list(
        dict.fromkeys(
            [
                f"provider:{provider_ref}",
                f"capability:{capability}",
                f"environment:{binding_fingerprint}",
                f"project:{_canonical_hash(str(request['project_root']))}",
                *safe_provenance_refs,
            ]
        )
    )
    if fallback_from:
        provenance.append(f"fallback_from:{str(_redact_sensitive(fallback_from))}")

    projected_target = _target_projection(
        resolution=resolution,
        environment_snapshot=environment_snapshot,
        provider_result=provider_result,
        explicit_target=target,
    )
    mutation = _mutation_provenance(
        request=request,
        provider_result=provider_result,
        explicit=mutation_provenance,
    )
    if "mutation_evidence" in observed and mutation is None:
        raise ValueError("mutation_evidence requires structured mutation provenance")

    canonical_material = {
        "provider_ref": provider_ref,
        "capability": capability,
        "project_root": str(request["project_root"]),
        "status": provider_status,
        "failure_class": failure_class,
        "observed_evidence": sorted(observed),
        "required_evidence": sorted(required),
        "completion": completion,
        "observation_state": observation_state,
        "environment": _environment_projection(environment_snapshot),
        "target": projected_target,
        "mutation_provenance": mutation,
    }
    evidence_status = _evidence_status(
        provider_status=provider_status,
        completion=completion,
        failure_class=failure_class,
    )
    if latency_ms is not None and float(latency_ms) < 0:
        raise ValueError("latency_ms must be non-negative")

    return {
        "schema_version": "1.1",
        "evidence_id": evidence_id,
        "run_id": run_id,
        "step_id": step_id,
        "producer": "tool_runtime",
        "source_type": "provider_result",
        "source_ref": structured_result_ref,
        "status": evidence_status,
        "payload_ref": structured_result_ref,
        "hash": _canonical_hash(canonical_material),
        "timestamp": timestamp or _now(),
        "provenance": provenance,
        "gate_outcome": None,
        "definition_fingerprint": deepcopy(dict(definition_fingerprint)),
        "capability": capability,
        "provider_ref": provider_ref,
        "project_root": str(request["project_root"]),
        "environment": _environment_projection(environment_snapshot),
        "target": projected_target,
        "safety_strength": provider.safety_strength,
        "evidence_strength": provider.evidence_strength,
        "completion": completion,
        "observation_state": observation_state,
        "failure_class": failure_class,
        "observed_evidence": sorted(observed),
        "required_evidence": sorted(required),
        "raw_refs": safe_raw_refs,
        "mutation_provenance": mutation,
        "latency_ms": None if latency_ms is None else float(latency_ms),
        "fallback_from": None if fallback_from is None else str(_redact_sensitive(fallback_from)),
        "durability": "current_run",
    }


def attach_capability_outcome(
    execution_result: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach one canonical capability outcome without changing semantic routing."""
    if execution_result.get("schema_version") not in {"1.0", "1.1"}:
        raise ValueError("unsupported ExecutionResult schema_version")
    if evidence.get("schema_version") != "1.1":
        raise ValueError("capability outcome requires Tool Runtime Evidence v1.1")
    if execution_result.get("run_id") != evidence.get("run_id"):
        raise ValueError("ExecutionResult and Evidence run_id differ")
    if execution_result.get("step_id") != evidence.get("step_id"):
        raise ValueError("ExecutionResult and Evidence step_id differ")

    value = deepcopy(dict(execution_result))
    refs = list(value.get("evidence_refs") or [])
    evidence_id = str(evidence.get("evidence_id") or "")
    if not evidence_id:
        raise ValueError("evidence_id is required")
    if evidence_id not in refs:
        refs.append(evidence_id)
    value["evidence_refs"] = refs

    outcomes = list(value.get("capability_outcomes") or [])
    outcomes.append(
        {
            "capability": str(evidence["capability"]),
            "provider_ref": str(evidence["provider_ref"]),
            "completion": str(evidence["completion"]),
            "status": str(evidence["status"]),
            "failure_class": evidence.get("failure_class"),
            "observation_state": str(evidence["observation_state"]),
            "evidence_refs": [evidence_id],
            "environment_profile": evidence["environment"].get("profile_hint"),
            "safety_strength": int(evidence["safety_strength"]),
            "evidence_strength": int(evidence["evidence_strength"]),
        }
    )
    value["capability_outcomes"] = outcomes
    value["schema_version"] = "1.1"
    return value
