#!/usr/bin/env python3
"""Migration-only legacy BehaviorEval -> Phase 1 canonical contract normalizer."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

INFRA_FAILURES = {
    "runtime_timeout", "runtime_protocol_failure", "evaluator_contract_failure",
    "task_fixture_invalid", "unavailable_required_evidence",
}
RUNTIME_FAILURES = INFRA_FAILURES - {"evaluator_contract_failure"}


class NormalizationError(ValueError):
    pass


def _yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise NormalizationError(f"missing required legacy file: {path}") from exc
    if not isinstance(value, dict):
        raise NormalizationError(f"legacy YAML root must be an object: {path}")
    return value


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NormalizationError(f"referenced legacy file is missing: {path}") from exc
    if not isinstance(value, dict):
        raise NormalizationError(f"legacy JSON root must be an object: {path}")
    return value


def _text(value: Any, fallback: str = "") -> str:
    return str(value or "").strip() or fallback


def _fingerprint(envelope: dict[str, Any]) -> dict[str, str]:
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
    ref = evidence.get("metrics_ref")
    if ref:
        root = bundle.resolve()
        path = (root / str(ref)).resolve()
        if path != root and root not in path.parents:
            raise NormalizationError("metrics_ref escapes bundle")
        return _json(path), path.relative_to(root).as_posix()
    fallback = bundle / "metrics.json"
    return (_json(fallback), "metrics.json") if fallback.is_file() else (None, None)


def _changed_paths(metrics: dict[str, Any] | None) -> dict[str, Any]:
    if metrics is None or "changed_paths" not in metrics:
        return {"observation_state": "not_observed", "paths": []}
    raw = metrics["changed_paths"]
    if not isinstance(raw, list) or any(not isinstance(x, str) or not x.strip() for x in raw):
        raise NormalizationError("metrics.changed_paths must be a non-empty-string array when present")
    paths = [x.replace("\\", "/").strip() for x in raw]
    if len(paths) != len(set(paths)):
        raise NormalizationError("metrics.changed_paths contains duplicate canonical paths")
    return {"observation_state": "observed", "paths": paths}


def _gates(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = envelope.get("evidence") or {}
    raw = evidence.get("gate_evidence") or []
    if not isinstance(raw, list):
        raise NormalizationError("evidence.gate_evidence must be an array")
    output = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise NormalizationError(f"gate_evidence[{index}] must be an object")
        gate_id = _text(item.get("id") or item.get("gate"))
        status = _text(item.get("status"))
        if not gate_id or status not in {"passed", "failed", "unavailable"}:
            raise NormalizationError(f"gate_evidence[{index}] has invalid id/status")
        requirement = _text(item.get("requirement"), "unknown")
        if requirement not in {"required", "conditional", "informational", "not_applicable", "unknown"}:
            requirement = "unknown"
        refs = item.get("evidence_refs") or []
        if not isinstance(refs, list) or any(not isinstance(x, str) or not x.strip() for x in refs):
            refs = []
        output.append({
            "gate_id": gate_id, "requirement": requirement, "status": status,
            "evidence_refs": refs,
            "detail": _text(item.get("evidence") or item.get("detail")) or None,
        })
    return output


def _failure(envelope: dict[str, Any], metrics: dict[str, Any] | None) -> tuple[str | None, str, str]:
    failure = envelope.get("failure") or {}
    if not isinstance(failure, dict):
        raise NormalizationError("failure must be an object when present")
    envelope_class = _text(failure.get("class")) or None
    metrics_class = None
    if metrics is not None and "failure_class" in metrics:
        raw = metrics.get("failure_class")
        if raw is not None and not isinstance(raw, str):
            raise NormalizationError("metrics.failure_class must be a string or null")
        metrics_class = _text(raw) or None
    if envelope_class and metrics_class and envelope_class != metrics_class:
        raise NormalizationError(
            f"failure class contradiction: envelope={envelope_class} metrics={metrics_class}"
        )
    failure_class = envelope_class or metrics_class
    state = _text(failure.get("observation_state"))
    if not state:
        state = "not_observed" if failure_class in INFRA_FAILURES else "observed"
    if state not in {"observed", "not_observed"}:
        raise NormalizationError("failure.observation_state is invalid")
    return failure_class, _text(failure.get("reason")), state


def normalize_bundle(bundle: Path) -> dict[str, Any]:
    bundle = bundle.expanduser().resolve()
    envelope = _yaml(bundle / "execution-envelope.yaml")
    run_id = _text(envelope.get("run_id"))
    if not run_id:
        raise NormalizationError("legacy envelope has no run_id")

    metrics, metrics_ref = _metrics(bundle, envelope)
    changed = _changed_paths(metrics)
    gates = _gates(envelope)
    failure_class, failure_reason, observation_state = _failure(envelope, metrics)
    fp = _fingerprint(envelope)
    executor = envelope.get("executor") or {}
    execution_fp = envelope.get("execution_fingerprint") or {}
    if not isinstance(executor, dict) or not isinstance(execution_fp, dict):
        raise NormalizationError("executor/execution_fingerprint must be objects")

    raw_status = _text(envelope.get("status"))
    if raw_status in {"completed", "passed", "ok"}:
        status = "passed"
    elif raw_status == "unavailable":
        status = "unavailable"
    elif raw_status in {"cancelled", "canceled"}:
        status = "cancelled"
    else:
        status = "failed"

    untyped_failure = status in {"failed", "unavailable"} and failure_class is None
    if untyped_failure:
        observation_state = "not_observed"

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
    refs = []
    for key in (
        "context_manifest", "response", "diff", "artifact_index", "metrics_ref",
        "codex_events_ref", "codex_stderr_ref",
    ):
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
    refs = list(dict.fromkeys(refs))
    step_id = f"legacy:{_text(envelope.get('golden_task_id'), run_id)}"

    execution_result = {
        "schema_version": "1.0",
        "run_id": run_id,
        "step_id": step_id,
        "action_id": f"legacy:{run_id}:execution",
        "status": status,
        "started_at": None,
        "completed_at": None,
        "exit_code": None,
        "runtime_failure": runtime_failure,
        "changed_paths": changed,
        "gate_outcomes": gates,
        "tool_identity": {
            "provider": _text(executor.get("provider"), "legacy-unavailable"),
            "model": _text(executor.get("model"), "legacy-unavailable"),
            "model_revision": _text(executor.get("model_revision"), "legacy-unavailable"),
            "tool_manifest_hash": _text(execution_fp.get("tool_manifest_hash"), "legacy-unavailable"),
            "executor_profile": _text(executor.get("profile")) or None,
            "execution_mode": _text(executor.get("mode")) or None,
        },
        "evidence_refs": refs,
        "telemetry_refs": [metrics_ref] if metrics_ref else [],
        "definition_fingerprint": fp,
        "compatibility": {
            "source_contract": "legacy-behavior-eval-envelope",
            "source_schema_version": _text(envelope.get("schema_version"), "unknown"),
            "synthetic_step_id": True,
            "synthetic_action_id": True,
        },
    }

    execution_evidence = []
    for index, gate in enumerate(gates):
        digest = hashlib.sha256(
            json.dumps(gate, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
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
            "hash": digest,
            "timestamp": None,
            "provenance": ["execution-envelope.yaml"],
            "gate_outcome": gate,
            "definition_fingerprint": fp,
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
        "evidence_refs": refs,
        "reason": failure_reason,
        "source_execution_result_ref": f"{run_id}:execution-result",
    }

    diagnostics = [
        "Legacy bundle has no canonical step/action identifiers; deterministic compatibility identifiers were assigned."
    ]
    diagnostics.append(
        "changed_paths was preserved from structured metrics.json and was not reparsed from diff text."
        if changed["observation_state"] == "observed"
        else "changed_paths was not recorded; empty paths must not be interpreted as a mutation no-op."
    )
    if untyped_failure:
        diagnostics.append(
            "Legacy bundle has no typed failure_class; failure attribution was intentionally not inferred from response/stderr text."
        )

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
