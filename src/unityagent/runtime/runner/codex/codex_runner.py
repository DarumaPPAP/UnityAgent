#!/usr/bin/env python3
"""Canonical Codex Runtime runner.

It executes one already-materialized task. It does not select Route/Graph, inject
Golden expectations, persist workflow state, or grade Agent quality.
"""
from __future__ import annotations
from unityagent.resources import resource_root
import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, SchemaError, ValidationError

ROOT = resource_root()

from unityagent.runtime.execution_control.process_runtime import run_streaming_process
from unityagent.runtime.guardrails.mutation_guard import evaluate_mutation_scope
from unityagent.runtime.guardrails.permission_guard import RuntimePermissionError, enforce_permission
from unityagent.runtime.sandbox.workspace_guard import changed_paths, snapshot_workspace, snapshot_workspace_hashes, workspace_path


class CodexRunnerError(ValueError):
    pass


def _request(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise CodexRunnerError("request must be schema_version 1.0 object")
    if "expectation" in data or "golden_expectation" in data:
        raise CodexRunnerError("Golden expectation is forbidden in Runtime request")
    for key in ("run_id", "step_id", "action_id", "workspace_root", "prompt", "definition_fingerprint"):
        if key not in data:
            raise CodexRunnerError(f"missing request field: {key}")
    execution = data.get("execution")
    if not isinstance(execution, dict) or not execution.get("profile") or not execution.get("work_kind"):
        raise CodexRunnerError("execution.profile and execution.work_kind are required")
    return data


def _command_prefix(raw: str | None) -> list[str]:
    source = raw or os.environ.get("CODEX_CLI_COMMAND_JSON", "").strip()
    if source:
        value = json.loads(source)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
            raise CodexRunnerError("Codex CLI command must be a non-empty JSON string array")
        return value
    executable = shutil.which("codex")
    if executable is None:
        raise CodexRunnerError("Codex CLI was not found on PATH")
    return [executable]


def _profile(profile_id: str) -> dict[str, Any]:
    source = yaml.safe_load((ROOT / "src/unityagent/runtime/profiles/runtime-profiles.yaml").read_text(encoding="utf-8")) or {}
    profiles = source.get("profiles", {}) or {}
    profile = profiles.get(profile_id)
    if not isinstance(profile, dict):
        raise CodexRunnerError(f"unknown Runtime execution profile: {profile_id}")
    return profile


def _runtime_failure(failure_class: str, reason: str, source_ref: str | None = None, *, retryable: bool = False, observed: bool = False) -> dict:
    return {"schema_version": "1.0", "failure_class": failure_class, "reason": reason, "retryable": retryable, "source_ref": source_ref, "observation_state": "observed" if observed else "not_observed"}


def _tool_identity(request: dict, model: str, provider: str) -> dict:
    identity = request.get("tool_identity", {}) or {}
    execution = request.get("execution", {}) or {}
    return {"provider": provider, "model": model, "model_revision": str(identity.get("model_revision") or model), "tool_manifest_hash": str(identity.get("tool_manifest_hash") or "runtime-codex-v1"), "executor_profile": identity.get("executor_profile") or execution.get("profile"), "execution_mode": identity.get("execution_mode")}


def _write_permission_denied(request: dict[str, Any], output: Path, *, model: str, provider: str, reason: str) -> dict:
    scope = request.get("mutation_scope", {}) or {}
    mutation = {
        "schema_version": "1.0", "mutation_id": f"{request['run_id']}:{request['step_id']}",
        "run_id": request["run_id"], "step_id": request["step_id"],
        "scope": {"allowed_paths": list(scope.get("allowed_paths", []) or []), "prohibited_paths": list(scope.get("prohibited_paths", []) or [])},
        "changed_paths": {"observation_state": "not_observed", "paths": []},
        "diff_ref": None, "before_fingerprint": None, "after_fingerprint": None,
        "scope_status": "not_observed", "verification_refs": [],
    }
    (output / "mutation-evidence.yaml").write_text(yaml.safe_dump(mutation, sort_keys=False, allow_unicode=True), encoding="utf-8")
    result = {
        "schema_version": "1.0", "run_id": request["run_id"], "step_id": request["step_id"], "action_id": request["action_id"],
        "status": "failed", "started_at": None, "completed_at": None, "exit_code": None,
        "runtime_failure": _runtime_failure("runtime_permission_denied", reason, "mutation-evidence.yaml"),
        "changed_paths": {"observation_state": "not_observed", "paths": []},
        "gate_outcomes": list(request.get("gate_outcomes", []) or []),
        "tool_identity": _tool_identity(request, model, provider),
        "evidence_refs": ["mutation-evidence.yaml"], "telemetry_refs": [],
        "definition_fingerprint": request["definition_fingerprint"],
    }
    (output / "execution-result.yaml").write_text(yaml.safe_dump(result, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps({"changed_paths": {"observation_state": "not_observed", "paths": []}, "runtime": {"launched": False}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def execute(request: dict[str, Any], output: Path, *, command_prefix: list[str], timeout_seconds: float, reasoning_effort: str) -> dict:
    if reasoning_effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}:
        raise CodexRunnerError("unsupported reasoning effort")
    workspace = workspace_path(request["workspace_root"])
    execution = request.get("execution", {}) or {}
    profile_id = str(execution.get("profile") or "").strip()
    work_kind = str(execution.get("work_kind") or "").strip()
    model = str((request.get("tool_identity") or {}).get("model") or "").strip()
    if not model:
        raise CodexRunnerError("tool_identity.model is required")
    provider = str((request.get("tool_identity") or {}).get("provider") or "openai")
    reasoning = execution.get("reasoning") is True
    if reasoning and any(not isinstance(request.get(key), str) or not request[key].strip() for key in ("original_workspace_root", "output_schema_path", "profile_id", "capability", "source_context_id", "source_context_fingerprint")):
        raise CodexRunnerError("reasoning request identity, workspace, or schema field is missing")
    original = workspace_path(request["original_workspace_root"]) if reasoning else None
    schema_path = Path(request["output_schema_path"]).resolve() if reasoning else None
    output_path = output.resolve()
    if reasoning:
        if profile_id != "generic_planning" or work_kind != "analysis" or execution.get("mutation_authorized") is True or request.get("mutation_scope"):
            raise CodexRunnerError("reasoning requires generic_planning analysis with empty mutation scope")
        if original == workspace or original in workspace.parents or workspace in original.parents:
            raise CodexRunnerError("reasoning workspace must be isolated from the original Project")
        if not schema_path.is_file() or workspace not in schema_path.parents:
            raise CodexRunnerError("reasoning output schema must be materialized in the isolated workspace")
        if output_path == original or original in output_path.parents or output_path == workspace or workspace in output_path.parents:
            raise CodexRunnerError("reasoning output must be outside the isolated and original workspaces")
    runtime_profile = _profile(profile_id)
    if reasoning and (runtime_profile.get("project_access") != "none" or runtime_profile.get("direct_mutation") is not False):
        raise CodexRunnerError("reasoning Runtime Profile must prohibit project access and direct mutation")
    output.mkdir(parents=True, exist_ok=True)

    try:
        enforce_permission(
            profile=runtime_profile, work_kind=work_kind,
            mutation_authorized=execution.get("mutation_authorized") is True,
            human_approval_required=execution.get("human_approval_required") is True,
            human_approval_granted=execution.get("human_approval_granted") is True,
        )
    except RuntimePermissionError as exc:
        return _write_permission_denied(request, output, model=model, provider=provider, reason=str(exc))

    before = snapshot_workspace(workspace, excluded_prefixes=(".unityagent-control",))
    original_before = snapshot_workspace_hashes(original) if original else None
    final_path = output / ("response.json" if reasoning else "response.md")
    events_path = output / "codex-events.jsonl"
    stderr_path = output / "codex-stderr.txt"
    sandbox_mode = "read-only" if work_kind in {"analysis", "verification"} else "workspace-write"
    command = [*command_prefix, "exec", "--ephemeral", "--json", "--skip-git-repo-check", "--sandbox", sandbox_mode, "--model", model, "-c", f'model_reasoning_effort="{reasoning_effort}"']
    if reasoning:
        command.append("--ignore-user-config")
    if schema_path:
        command.extend(["--output-schema", str(schema_path)])
    command.extend(["--output-last-message", str(final_path), "--cd", str(workspace), "-"])
    process = run_streaming_process(
        command,
        cwd=workspace,
        timeout_seconds=timeout_seconds,
        stdout_path=events_path,
        stderr_path=stderr_path,
        stdin_text=str(request["prompt"]),
    )
    after = snapshot_workspace(workspace, excluded_prefixes=(".unityagent-control",))
    changed = changed_paths(before, after)
    original_changed = changed_paths(original_before, snapshot_workspace_hashes(original)) if original else []
    scope = request.get("mutation_scope", {}) or {}
    guard = evaluate_mutation_scope(work_kind=work_kind, changed_paths=changed, allowed_paths=list(scope.get("allowed_paths", []) or []), prohibited_paths=list(scope.get("prohibited_paths", []) or []))

    failure = None
    status = "passed"
    if process.timed_out:
        status = "failed"
        failure = _runtime_failure("runtime_timeout", f"Codex exceeded {timeout_seconds} seconds", "codex-stderr.txt", retryable=True)
    elif process.cancelled:
        status = "cancelled"
        failure = _runtime_failure("runtime_cancelled", "Codex execution was cancelled", "codex-stderr.txt")
    elif process.returncode != 0:
        status = "failed"
        failure = _runtime_failure("runtime_protocol_failure", f"Codex exited with code {process.returncode}", "codex-stderr.txt", retryable=True)
    elif guard["status"] != "passed":
        status = "failed"
        failure = _runtime_failure("mutation_attempt_detected" if reasoning else "runtime_permission_denied", str(guard["reason"]), "mutation-evidence.yaml", observed=True)
    if original_changed:
        status = "failed"
        failure = _runtime_failure("mutation_attempt_detected", f"original workspace changed: {original_changed}", "mutation-evidence.yaml", observed=True)
    if reasoning and status == "passed":
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            structured = json.loads(final_path.read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(structured)
        except (OSError, ValueError, KeyError, SchemaError, ValidationError) as exc:
            status = "failed"
            failure = _runtime_failure("structured_output_invalid", str(exc), "response.json", observed=True)

    mutation = {"schema_version": "1.0", "mutation_id": f"{request['run_id']}:{request['step_id']}", "run_id": request["run_id"], "step_id": request["step_id"], "scope": {"allowed_paths": list(scope.get("allowed_paths", []) or []), "prohibited_paths": list(scope.get("prohibited_paths", []) or [])}, "changed_paths": {"observation_state": "observed", "paths": changed}, "diff_ref": None, "before_fingerprint": None, "after_fingerprint": None, "scope_status": guard["scope_status"], "verification_refs": []}
    (output / "mutation-evidence.yaml").write_text(yaml.safe_dump(mutation, sort_keys=False, allow_unicode=True), encoding="utf-8")
    result = {"schema_version": "1.0", "run_id": request["run_id"], "step_id": request["step_id"], "action_id": request["action_id"], "status": status, "started_at": None, "completed_at": None, "exit_code": process.returncode, "runtime_failure": failure, "changed_paths": {"observation_state": "observed", "paths": changed}, "gate_outcomes": list(request.get("gate_outcomes", []) or []), "tool_identity": _tool_identity(request, model, provider), "evidence_refs": ["codex-events.jsonl", "codex-stderr.txt", "mutation-evidence.yaml"], "telemetry_refs": [], "definition_fingerprint": request["definition_fingerprint"]}
    if reasoning:
        result.update({"sandbox_mode": sandbox_mode, "original_workspace_changed_paths": original_changed, "structured_output_ref": "response.json" if final_path.is_file() else None, "source_context_id": request["source_context_id"], "source_context_fingerprint": request["source_context_fingerprint"], "reasoning_provenance": {"profile_id": request["profile_id"], "capability": request["capability"], "runtime_profile": profile_id, "model": model, "model_provider": provider, "model_revision": _tool_identity(request, model, provider)["model_revision"], "reasoning_effort": reasoning_effort}})
        result["telemetry_refs"] = ["metrics.json"]
        if final_path.is_file():
            result["evidence_refs"].append("response.json")
    (output / "execution-result.yaml").write_text(yaml.safe_dump(result, sort_keys=False, allow_unicode=True), encoding="utf-8")
    metrics = {"changed_paths": changed, "original_workspace_changed_paths": original_changed, "runtime": {"launched": True, "timed_out": process.timed_out, "cancelled": process.cancelled, "duration_seconds": process.duration_seconds, "process_tree_cleanup": process.process_tree_cleanup, "remaining_processes": process.remaining_processes, "event_count": process.event_count, "sandbox_mode": sandbox_mode}}
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--command-json")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--reasoning-effort", default="high")
    args = parser.parse_args(argv)
    try:
        request = _request(args.request)
        result = execute(request, args.output, command_prefix=_command_prefix(args.command_json), timeout_seconds=args.timeout_seconds, reasoning_effort=args.reasoning_effort)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 30
    print(json.dumps({"status": result["status"], "run_id": result["run_id"]}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 10


if __name__ == "__main__":
    raise SystemExit(main())
