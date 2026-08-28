#!/usr/bin/env python3
"""Normalize legacy BehaviorEval bundles into Phase 1 canonical contracts.

Migration-only adapter: preserve structured legacy facts, fail closed on
contradictions, and never infer mutation/no-op or Agent quality from missing data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

INFRA_FAILURES = {
    "runtime_timeout",
    "runtime_protocol_failure",
    "evaluator_contract_failure",
    "task_fixture_invalid",
    "unavailable_required_evidence",
}
RUNTIME_FAILURES = {
    "runtime_timeout",
    "runtime_protocol_failure",
    "task_fixture_invalid",
    "unavailable_required_evidence",
}


class NormalizationError(ValueError):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise NormalizationError(f"missing required legacy file: {path}") from exc
    if not isinstance(value, dict):
        raise NormalizationError(f"legacy YAML root must be an object: {path}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NormalizationError(f"referenced legacy file is missing: {path}") from exc
    if not isinstance(value, dict):
        raise NormalizationError(f"legacy JSON root must be an object: {path}")
    return value


def _text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _definition_fingerprint(envelope: dict[str, Any]) -> dict[str, str]:
    fp = envelope.get("execution_fingerprint") or {}
    if not isinstance(fp, dict):
        raise NormalizationError("execution_fingerprint must be an object")
    unityagent = _text(fp.get("unityagent_revision"), "legacy-unavailable")
    return {
        "schema_version": "1.0",
        "architecture_version": "legacy-pre-canonical",
        "policy_revision": unityagent,
        "prompt_revision": unityagent,
        "context_revision": unityagent,
        "graph_revision": _text(fp.get("graph_engineering_revision"), "legacy-unavailable"),
        "runtime_profile_revision": _text(fp.get("execution_profile"), "legacy-unavailable"),
        "tool_schema_revision": _text(fp.get("tool_manifest_hash"), "legacy-unavailable"),
        "checkpoint_schema_revision": "legacy-unavailable",
        "evidence_schema_revision": _text(envelope.get("schema_version"), "legacy-unavailable"),
        "eval_contract_revision": _text(fp.get("golden_suite_revision"), "legacy-unavailable"),
    }


def _metrics(bundle: Path, envelope: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    evidence = envelope.get("evidence") or {}
    if not isinstance(evidence, dict):
        raise NormalizationError("evidence must be an object")
    metrics_ref = evidence.get("metrics_ref")
    if metrics_ref:
        root = bundle.resolve()
        path = (root / str(metrics_ref)).resolve()
        if path != root and root not in path.parents:
            raise NormalizationError("metrics_ref escapes bundle")
        return _load_json(path), path.relative_to(root).as_posix()
    fallback = bundle / "metrics.json"
    if fallback.is_file():
        return _load_json(fallback), "metrics.json"
    return None, None


def _changed_paths(metrics: dict[str, Any] | None) -> dict[str, Any]:
    if metrics is None or "changed_paths" not in metrics:
        return {"observation_state": "not_observed", "paths": []}
    raw = metrics["changed_paths"]
    if not isinstance(raw, list) or any(not isinstance(item, str) or not item.strip() for item in raw):
        raise NormalizationError("metrics.changed_paths must be a non-empty-string array when present")
    paths = [item.replace("\\", "/").strip() for item in raw]
    if len(paths) != len(set(paths)):
        raise NormalizationError("metrics.changed_paths contains duplicate canonical paths")
    return {"observation_state": "observed", "paths": paths}


def _gate_outcomes(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = envelope.get("evidence") or {}
    raw = evidence.get("gate_evidence") or []
    if not isinstance(raw, list):
        raise NormalizationError("evidence.gate_evidence must be an array")
    output: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise NormalizationError(f"gate_evidence[{index}] must be an object")
        gate_id = _text(item.get("id") or item.get("gate"), "")
        status = str(item.get("status") or "").strip()
        if not gate_id or status not in {"passed", "failed", "unavailable"}:
            raise NormalizationError(f"gate_evidence[{index}] has invalid id/status")
        requirement = str(item.get("requirement") or "unknown").strip()
        if requirement not in {"required", "conditional", "informational", "not_applicable", "unknown"}:
            requirement = "unknown"
        refs = item.get("evidence_refs") or []
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            refs = []
        output.append({
            "gate_id": gate_id,
            "requirement": requirement,
            "status": status,
            "evidence_refs": refs,
            "detail": str(item.get("evidence") or item.get("detail") or "") or None,
        })
    return output


def _failure(envelope: dict[str, Any]) -> tuple[str | None, str, str]:
    failure = envelope.get("failure") or {}
    if not isinstance(failure, dict):
        raise NormalizationError("failure must be an object when present")
    failure_class = str(failure.get("class") or "").strip() or None
    reason = str(failure.get("reason") or "")
    state = str(failure.get("observation_state") or "").strip()
    if not state:
        state = "not_observed" if failure_class in INFRA_FAILURES else "observed"
    if state not in {"observed", "not_observed"}:
        raise NormalizationError("failure.observation_state is invalid")
    return failure_class, reason, state


def normalize_bundle(bundle: Path) -> dict[str, Any]:
    bundle = bundle.expanduser().resolve()
    envelope = _load_yaml(bundle / "execution-envelope.yaml")
    run_id = _text(envelope.get("run_id"), "")
    if not run_id:
        raise NormalizationError("legacy envelope has no run_id")

    metrics, metrics_ref = _metrics(bundle, envelope)
    changed_paths = _changed_paths(metrics)
    gates = _gate_outcomes(envelope)
    failure_class, failure_reason, observation_state = _failure(envelope)
    fingerprint = _definition_fingerprint(envelope)
    executor = envelope.get("executor") or {}
    execution_fp = envelope.get("execution_fingerprint") or {}
    if not isinstance(executor, dict) or not isinstance(execution_fp, dict):
        raise NormalizationError("executor/execution_fingerprint must be objects")

    step_id = f"legacy:{_text(envelope.get('golden_task_id'), run_id)}"
    action_id = f"legacy:{run_id}:execution"
    raw_status = str(envelope.get("status") or "").strip()
    if raw_status in {"completed", "passed", "ok"}:
        status = "passed"
    elif raw_status == "unavailable":
        status = "unavailable"
    elif raw_status in {"cancelled", "canceled"}:
        status = "cancelled"
    else:
        status = "failed"

    runtime_failure = None
    if failure_class in RUNTIME_FAILURES:
        runtime_failure = {
            "schema_version": "1.0",
            "failure_class": failure_class,
            "reason": failure_reason or failure_class,
            "retryable": failure_class in {"runtime_timeout", "runtime_protocol_failure"},
            "source_ref": "execution-envelope.yaml",
            "observation_state": "not_observed",
        }

    evidence = envelope.get("evidence") or {}
    evidence_refs = []
    for key in ("context_manifest", "response", "diff", "artifact_index", "metrics_ref"):
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            evidence_refs.append(value.strip())
    evidence_refs = list(dict.fromkeys(evidence_refs))

    execution_result = {
        "schema_version": "1.0",
        "run_id": run_id,
        "step_id": step_id,
        "action_id": action_id,
        "status": status,
        "started_at": None,
        "completed_at": None,
        "exit_code": None,
        "runtime_failure": runtime_failure,
        "changed_paths": changed_paths,
        "gate_outcomes": gates,
        "tool_identity": {
            "provider": _text(executor.get("provider"), "legacy-unavailable"),
            "model": _text(executor.get("model"), "legacy-unavailable"),
            "model_revision": _text(executor.get("model_revision"), "legacy-unavailable"),
            "tool_manifest_hash": _text(execution_fp.get("tool_manifest_hash"), "legacy-unavailable"),
            "executor_profile": str(executor.get("profile") or "") or None,
            "execution_mode": str(executor.get("mode") or "") or None,
        },
        "evidence_refs": evidence_refs,
        "telemetry_refs": [metrics_ref] if metrics_ref else [],
        "definition_fingerprint": fingerprint,
        "compatibility": {
            "source_contract": "legacy-behavior-eval-envelope",
            "source_schema_version": str(envelope.get("schema_version") or "unknown"),
            "synthetic_step_id": True,
            "synthetic_action_id": True,
        },
    }

    execution_evidence = []
    for index, gate in enumerate(gates):
        payload = json.dumps(gate, sort_keys=True, ensure_ascii=False).encode("utf-8")
        execution_evidence.append({
            "schema_version": "1.0",
            "evidence_id": f"{run_id}:legacy-gate:{index}",
            "run_id": run_id,
            "step_id": step_id,
            "producer": "legacy-bundle-normalizer",
            "source_type": "quality_gate",
            "source_ref": "execution-envelope.yaml",
            "status": gate["status"],
            "payload_ref": None,
            "hash": hashlib.sha256(payload).hexdigest(),
            "timestamp": None,
            "provenance": ["execution-envelope.yaml"],
            "gate_outcome": gate,
            "definition_fingerprint": fingerprint,
        })

    denominator = observation_state == "observed" and failure_class not in INFRA_FAILURES
    eval_record = {
        "schema_version": "1.0",
        "eval_id": f"{run_id}:legacy-eval",
        "run_id": run_id,
        "observation_state": observation_state,
        "failure_class": failure_class,
        "quality_denominator_eligible": denominator,
        "runtime_failure_ref": f"{run_id}:runtime-failure" if runtime_failure else None,
        "evidence_refs": evidence_refs,
        "reason": failure_reason,
        "source_execution_result_ref": f"{run_id}:execution-result",
    }

    diagnostics = [
        "Legacy bundle has no canonical step/action identifiers; deterministic compatibility identifiers were assigned."
    ]
    if changed_paths["observation_state"] == "not_observed":
        diagnostics.append("changed_paths was not recorded; empty paths must not be interpreted as a mutation no-op.")
    else:
        diagnostics.append("changed_paths was preserved from structured metrics.json and was not reparsed from diff text.")

    return {
        "schema_version": "1.0",
        "source_bundle": "execution-envelope.yaml",
        "execution_result": execution_result,
        "execution_evidence": execution_evidence,
        "mutation_evidence": None,
        "eval_record": eval_record,
        "diagnostics": diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = normalize_bundle(args.bundle)
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError, NormalizationError) as exc:
        print(f"legacy bundle normalization failed: {exc}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
