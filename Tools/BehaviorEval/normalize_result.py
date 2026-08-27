#!/usr/bin/env python3
"""Normalize an Actual Behavior evidence bundle into the Golden Candidate Result shape."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from derive_signals import derive_signals

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_CASES = ROOT / "Tests" / "GoldenTasks" / "cases.yaml"
BEHAVIOR_SUITES = ROOT / "Tests" / "BehaviorEval" / "suites.yaml"

FORBIDDEN_SECRET_KEYS = {
    "api_key", "apikey", "authorization", "auth_header", "secret", "access_token",
    "refresh_token", "raw_environment", "environment_variables", "credentials",
}
INFRASTRUCTURE_FAILURES = {
    "evaluator_contract_failure",
    "runtime_timeout",
    "runtime_protocol_failure",
    "unavailable_required_evidence",
    "task_fixture_invalid",
}


class BehaviorEvidenceError(ValueError):
    """Evidence bundle is malformed or violates the protocol."""


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise BehaviorEvidenceError(f"Expected mapping: {path}")
    return data


def _canonical_node_id(entry: Any, prefix: str) -> str:
    if isinstance(entry, str):
        value = entry
    elif isinstance(entry, dict):
        value = str(entry.get("id") or entry.get("node_id") or "")
        source_path = str(entry.get("source_path") or "")
        if not value and "#" in source_path:
            value = source_path.rsplit("#", 1)[-1]
        if prefix == "policy" and value and "#" in source_path:
            fragment = source_path.rsplit("#", 1)[-1]
            if fragment and fragment != value:
                raise BehaviorEvidenceError(
                    f"Policy provenance mismatch: id={value} source fragment={fragment}"
                )
    else:
        value = ""
    if value.startswith(prefix + ":"):
        return value.split(":", 1)[1]
    return value


def assert_no_secret_fields(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_SECRET_KEYS:
                raise BehaviorEvidenceError(f"Forbidden secret field in evidence envelope: {path}.{key}")
            assert_no_secret_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_secret_fields(child, f"{path}[{index}]")


def resolve_case_path(case_dir: Path, reference: str | None, *, required: bool) -> Path | None:
    if reference is None or str(reference).strip() in {"", "null", "None"}:
        if required:
            raise BehaviorEvidenceError("Required evidence reference is missing.")
        return None
    raw = Path(str(reference))
    if raw.is_absolute():
        raise BehaviorEvidenceError(f"Evidence reference must be case-relative: {reference}")
    root = case_dir.resolve()
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise BehaviorEvidenceError(f"Evidence path escapes case directory: {reference}") from exc
    if required and not resolved.is_file():
        raise BehaviorEvidenceError(f"Required evidence file does not exist: {reference}")
    return resolved


def _read_optional_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _gate_map(manifest: dict, envelope: dict) -> dict[str, str]:
    gates: dict[str, str] = {}
    for gate in ((manifest.get("harness", {}) or {}).get("quality_gates", []) or []):
        if not isinstance(gate, dict):
            continue
        gate_id = str(gate.get("id") or gate.get("node_id") or "")
        if gate_id.startswith("gate:"):
            gate_id = gate_id.split(":", 1)[1]
        status = str(gate.get("status") or "")
        if gate_id and status and status != "not_applicable":
            gates[gate_id] = status
    for evidence in ((manifest.get("execution", {}) or {}).get("evidence", []) or []):
        if not isinstance(evidence, dict):
            continue
        gate_id = str(evidence.get("gate") or "")
        status = str(evidence.get("status") or "")
        if gate_id and status and status != "not_applicable":
            gates[gate_id] = status
    for evidence in ((envelope.get("evidence", {}) or {}).get("gate_evidence", []) or []):
        if not isinstance(evidence, dict):
            continue
        gate_id = str(evidence.get("gate") or evidence.get("id") or "")
        status = str(evidence.get("status") or "")
        if gate_id and status and status != "not_applicable":
            gates[gate_id] = status
    return gates


def _unresolved(manifest: dict) -> list[str]:
    output: list[str] = []
    for item in ((manifest.get("execution", {}) or {}).get("unresolved_bindings", []) or []):
        if isinstance(item, str):
            output.append(item)
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("id") or "")
            if name:
                output.append(name)
    return sorted(set(output))


def _read_artifacts(case_dir: Path, artifact_index_path: Path) -> tuple[list[dict], list[dict]]:
    index = load_yaml(artifact_index_path)
    records: list[dict] = []
    candidate_generated: list[dict] = []
    for entry in index.get("artifacts", []) or []:
        if not isinstance(entry, dict):
            raise BehaviorEvidenceError("artifact-index.yaml entries must be mappings.")
        reference = str(entry.get("path") or "")
        path = resolve_case_path(case_dir, reference, required=True)
        assert path is not None
        language = str(entry.get("language") or "").strip().lower()
        kind = str(entry.get("kind") or "").strip()
        source = ""
        if language in {"csharp", "c#", "cs"}:
            source = path.read_text(encoding="utf-8", errors="replace")
        try:
            repo_relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            repo_relative = path.as_posix()
        record = {
            "path": repo_relative,
            "evidence_path": reference.replace("\\", "/"),
            "language": language,
            "kind": kind,
            "source": source,
        }
        records.append(record)
        if kind == "generated_source":
            candidate_generated.append({"path": repo_relative, "language": language, "kind": kind})
    return records, candidate_generated


def _failure_class(envelope: dict) -> str:
    failure = envelope.get("failure", {}) or {}
    if isinstance(failure, dict):
        value = str(failure.get("class") or "").strip()
        if value:
            return value
    return str(envelope.get("failure_class") or "").strip()


def normalize_case_result(case_dir: Path, case: dict, suite_case: dict) -> dict:
    case_dir = case_dir.resolve()
    envelope_path = case_dir / "execution-envelope.yaml"
    if not envelope_path.is_file():
        raise BehaviorEvidenceError(f"Missing execution-envelope.yaml: {case_dir}")

    envelope = load_yaml(envelope_path)
    assert_no_secret_fields(envelope)
    task_id = str(case.get("id") or "")
    if str(envelope.get("golden_task_id") or "") != task_id:
        raise BehaviorEvidenceError(
            f"Envelope golden_task_id mismatch: expected {task_id}, got {envelope.get('golden_task_id')}"
        )

    failure_class = _failure_class(envelope)
    status = str(envelope.get("status") or "")
    infrastructure_failure = failure_class in INFRASTRUCTURE_FAILURES
    observation_state = "not_observed" if infrastructure_failure else "observed"

    evidence = envelope.get("evidence", {}) or {}
    manifest_path = resolve_case_path(case_dir, evidence.get("context_manifest"), required=True)
    response_path = resolve_case_path(case_dir, evidence.get("response"), required=True)
    artifact_index_path = resolve_case_path(case_dir, evidence.get("artifact_index"), required=True)
    diff_path = resolve_case_path(case_dir, evidence.get("diff"), required=False)
    assert manifest_path is not None and response_path is not None and artifact_index_path is not None

    manifest = load_yaml(manifest_path)
    response_text = _read_optional_text(response_path)
    diff_text = _read_optional_text(diff_path)
    artifact_records, candidate_generated = _read_artifacts(case_dir, artifact_index_path)
    manifest_task = manifest.get("task", {}) or {}
    route = str(manifest_task.get("route") or "")
    fingerprint = manifest_task.get("fingerprint")
    gates = _gate_map(manifest, envelope)

    policies = sorted({
        policy_id
        for policy_id in (
            _canonical_node_id(entry, "policy")
            for entry in ((manifest.get("policy", {}) or {}).get("loaded", []) or [])
        )
        if policy_id
    })
    knowledge = sorted({
        knowledge_id
        for knowledge_id in (
            _canonical_node_id(entry, "knowledge")
            for entry in ((manifest.get("knowledge", {}) or {}).get("loaded", []) or [])
        )
        if knowledge_id
    })

    if observation_state == "observed":
        derived = derive_signals(
            case,
            suite_case,
            manifest_route=route,
            response_text=response_text,
            diff_text=diff_text,
            artifacts=artifact_records,
            gates=gates,
        )
    else:
        derived = {
            "signals": [],
            "failure_types": [],
            "findings": [{
                "code": "BEHAVIOR_NOT_OBSERVED",
                "severity": "warning",
                "message": f"Agent behavior was not observed because {failure_class} occurred.",
            }],
            "evidence_coverage": {"covered_invariants": 0, "total_invariants": 0, "rate": 0.0, "sources": []},
            "structure": {},
        }

    failure_types = set(derived.get("failure_types", []) or [])
    if failure_class:
        failure_types.add(failure_class)

    if infrastructure_failure:
        outcome = "unavailable" if failure_class in {"runtime_timeout", "unavailable_required_evidence"} else "failed"
    elif status == "completed":
        outcome = "passed"
    elif status == "unavailable":
        outcome = "unavailable"
        failure_types.add("unavailable_evidence")
    elif status == "protocol_error":
        outcome = "failed"
        failure_types.add("broken_eval")
    elif status == "failed":
        outcome = "failed"
        failure_types.add("agent_behavior_regression")
    else:
        outcome = "failed"
        failure_types.add("broken_eval")

    attempt = envelope.get("attempt", {}) or {}
    agent_attempt = max(1, int(attempt.get("agent_attempt", 1)))
    execution_fingerprint = envelope.get("execution_fingerprint", {}) or {}
    result = {
        "task_id": task_id,
        "route": route,
        "fingerprint": fingerprint,
        "applied_policies": policies,
        "gates": gates,
        "signals": list(derived.get("signals", []) or []),
        "knowledge": knowledge,
        "unresolved": _unresolved(manifest),
        "failure_types": sorted(failure_types),
        "failure_class": failure_class,
        "outcome": outcome,
        "attempt_count": agent_attempt,
        "manifest_path": manifest_path.resolve().relative_to(ROOT.resolve()).as_posix()
        if manifest_path.resolve().is_relative_to(ROOT.resolve()) else manifest_path.as_posix(),
        "generated_artifacts": candidate_generated,
        "execution": {
            "mode": "actual_behavior",
            "run_id": str(envelope.get("run_id") or ""),
            "observation_state": observation_state,
            "failure_class": failure_class,
            "execution_fingerprint": execution_fingerprint,
            "evidence_provenance": {
                "route": "context_manifest" if observation_state == "observed" else "not_observed",
                "fingerprint": "context_manifest" if observation_state == "observed" else "not_observed",
                "gates": "context_manifest_and_execution_evidence",
                "knowledge": "context_manifest",
                "signals": ["source_structure", "mutation_diff", "evidence_claims", "context_manifest"]
                if observation_state == "observed" else [],
                "generated_artifacts": "artifact_index",
            },
            "evidence_coverage": derived.get("evidence_coverage", {}),
            "behavior_findings": list(derived.get("findings", []) or []),
            "structure": derived.get("structure", {}),
            "execution_owner": envelope.get("execution_owner", {}),
            "runtime": envelope.get("runtime", {}) or {},
        },
    }
    return result


def _find_case(task_id: str) -> dict:
    suite = load_yaml(GOLDEN_CASES)
    for case in suite.get("cases", []) or []:
        if isinstance(case, dict) and case.get("id") == task_id:
            return case
    raise BehaviorEvidenceError(f"Unknown Golden Task: {task_id}")


def _find_suite_case(suite_id: str, task_id: str) -> dict:
    suites = load_yaml(BEHAVIOR_SUITES).get("suites", {}) or {}
    suite = suites.get(suite_id, {}) or {}
    for case in suite.get("cases", []) or []:
        if isinstance(case, dict) and case.get("golden_task_id") == task_id:
            return case
    raise BehaviorEvidenceError(f"Golden Task {task_id} is not in Behavior suite {suite_id}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--golden-task-id", required=True)
    parser.add_argument("--suite", default="smoke")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = normalize_case_result(
            Path(args.case_dir), _find_case(args.golden_task_id), _find_suite_case(args.suite, args.golden_task_id)
        )
    except (OSError, UnicodeError, yaml.YAMLError, BehaviorEvidenceError, ValueError) as exc:
        print(f"Behavior result normalization failed: {exc}")
        return 30
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(result, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
