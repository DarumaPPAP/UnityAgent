#!/usr/bin/env python3
"""Execute Phase 8 one-repo Production Smoke through canonical UnityAgent authorities.

This integration harness coordinates the test only. Orchestration selects Route/Profile,
Context materializes input, Runtime owns the Codex process and hard enforcement,
Persistence stores immutable execution evidence, and Eval grades afterward in a
separate step.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.sax.saxutils
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Context.Assembly.materialize_context import materialize_context
from Eval.Datasets.paths import canonicalize_repo_path
from Orchestration.Routing.route_selector import load_routes, select_route
from Persistence.Evidence.evidence_store import EvidenceStore
from Persistence.Evidence.runtime_adapter import from_runtime_execution_evidence

SUITES = ROOT / "Eval/Datasets/Behavior/suites.yaml"
CONTRACTS = ROOT / "Eval/Datasets/Behavior/production-smoke-contracts.yaml"
ROUTES = ROOT / "Orchestration/Routing/task-routes.yaml"
RUNTIME = ROOT / "Runtime/Runner/Codex/codex_runner.py"
DEFAULT_ROOT = ROOT / "Artifacts/ProductionSmoke"
FAKE_MARKERS = ("fake_codex_cli.py", "fake_production_agent.py")


class ProductionSmokeError(ValueError):
    pass


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ProductionSmokeError(f"expected YAML mapping: {path}")
    return value


def _safe_run_id(raw: str | None) -> str:
    value = raw or datetime.now(timezone.utc).strftime("phase8-one-repo-%Y%m%d-%H%M%S")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", value) or value in {".", ".."}:
        raise ProductionSmokeError("run-id must be one safe path segment")
    return value


def _runtime_work_kind(eval_work_kind: str) -> str:
    mapping = {"implementation": "mutation", "analysis": "analysis", "verification": "verification"}
    try:
        return mapping[eval_work_kind]
    except KeyError as exc:
        raise ProductionSmokeError(f"unsupported Eval work_kind: {eval_work_kind}") from exc


def _fingerprint(prompt: str, eval_work_kind: str, allowed_paths: list[str], observed: list[dict[str, Any]]) -> dict[str, str]:
    """Classify the user-realistic task without reading Golden expectations or expected route."""
    lowered = prompt.lower()
    if eval_work_kind == "implementation":
        return {
            "intent": "fix" if ("compile" in lowered or "error" in lowered or "エラー" in prompt) else "implement",
            "artifact": "csharp",
            "scope": "local" if len(allowed_paths) <= 1 else "multi_source",
            "failure_mode": "compile" if ("compile" in lowered or "エラー" in prompt) else "none",
            "architecture_state": "decided",
            "mutation_target": "source",
            "evidence_state": "known",
            "project_access": "authorized",
        }
    if eval_work_kind == "verification":
        scope_text = " ".join(str(item.get("scope") or "") for item in observed)
        return {
            "intent": "review",
            "artifact": "csharp" if ".cs" in scope_text.lower() or "c#" in lowered or "compile" in lowered else "architecture",
            "scope": "local" if scope_text else "read_only",
            "failure_mode": "none",
            "architecture_state": "not_applicable",
            "mutation_target": "none",
            "evidence_state": "known" if observed else "partial",
            "project_access": "not_required",
        }
    return {
        "intent": "design" if ("設計" in prompt or "design" in lowered or "type" in lowered) else "review",
        "artifact": "architecture",
        "scope": "local",
        "failure_mode": "none",
        "architecture_state": "undecided",
        "mutation_target": "none",
        "evidence_state": "known",
        "project_access": "not_required",
    }


def _bindings(route_id: str, prompt: str, workspace: Path, allowed_paths: list[str]) -> dict[str, Any]:
    if route_id == "architecture-design":
        return {
            "goal": prompt,
            "scope_classification": "local_behavior",
            "prohibited_changes": "Do not implement and do not add unrequested abstraction.",
        }
    if route_id == "csharp-local-fix":
        target = allowed_paths[0] if allowed_paths else "CameraDebugger.cs"
        return {"target_source": str((workspace / target).resolve())}
    if route_id == "generic-planning":
        return {"goal": prompt}
    return {"goal": prompt}


def _selected_context_text(view: dict[str, Any]) -> str:
    selected = view.get("selected_refs") or {}
    records: list[dict[str, Any]] = []
    for key in ("policy", "context_pack", "primary_skill", "task_contract", "required_context", "conditional_context", "knowledge"):
        raw = selected.get(key)
        if isinstance(raw, dict):
            records.append(raw)
        elif isinstance(raw, list):
            records.extend(item for item in raw if isinstance(item, dict))
    seen: set[str] = set()
    chunks: list[str] = []
    for record in records:
        relative = str(record.get("resolved_path") or "")
        if not relative or relative in seen:
            continue
        seen.add(relative)
        path = (ROOT / relative).resolve()
        if path.is_file():
            chunks.append(f"\n--- BEGIN {relative} ---\n{path.read_text(encoding='utf-8')}\n--- END {relative} ---")
    return "\n".join(chunks)


def _prompt(production_prompt: str, view: dict[str, Any]) -> str:
    return f"""You are executing a controlled UnityAgent Production Smoke case.

USER TASK
{production_prompt}

CANONICAL CONTEXT
{_selected_context_text(view)}

OUTPUT PROTOCOL
Return only one JSON object in the final response:
{{
  "answer": "<Japanese task answer>",
  "loaded_policies": [
    {{"id": "<leaf clause id>", "source_path": "Policy/User/user-policy.yaml#<exact dotted fragment>", "reason": "<why it was applied>"}}
  ],
  "quality_gates": [
    {{"id": "<gate id>", "status": "passed|failed|unavailable", "evidence": "<specific evidence>"}}
  ],
  "unverified_conditions": ["<anything not actually verified>"]
}}

Rules:
- Report only policy clauses actually applied.
- Never invent a passed gate. Use unavailable when the evidence or tool is unavailable.
- Do not claim Unity Editor, Runtime, Player, target-device, visual, or performance verification unless it actually occurred.
- Keep all mutation inside the provided workspace and only inside allowed paths.
- The final response must not mention Golden expectations, expected route, hidden graders, or test answers.
"""


def _parse_response(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1])
            if stripped.lstrip().startswith("json"):
                stripped = stripped.lstrip()[4:].lstrip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProductionSmokeError("Codex final response is not the required JSON object") from exc
    if not isinstance(value, dict) or not isinstance(value.get("answer"), str):
        raise ProductionSmokeError("Codex final response must contain string answer")
    for key in ("loaded_policies", "quality_gates", "unverified_conditions"):
        if not isinstance(value.get(key), list):
            raise ProductionSmokeError(f"Codex final response must contain list {key}")
    return value


def _resolve_fragment(data: Any, fragment: str) -> bool:
    current = data
    for part in [item for item in fragment.split(".") if item]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _validated_policies(structured: dict[str, Any]) -> list[dict[str, str]]:
    policy = _yaml(ROOT / "Policy/User/user-policy.yaml")
    output: list[dict[str, str]] = []
    for item in structured.get("loaded_policies") or []:
        if not isinstance(item, dict):
            raise ProductionSmokeError("loaded_policies entries must be objects")
        policy_id = str(item.get("id") or "").strip()
        source = str(item.get("source_path") or "").strip()
        reason = str(item.get("reason") or "").strip()
        prefix = "Policy/User/user-policy.yaml#"
        if not policy_id or not source.startswith(prefix) or not reason:
            raise ProductionSmokeError("loaded policy must use canonical user-policy source with exact fragment")
        fragment = source[len(prefix):]
        if fragment.split(".")[-1] != policy_id or not _resolve_fragment(policy, fragment):
            raise ProductionSmokeError(f"policy id/source mismatch: {policy_id} vs {source}")
        output.append({"id": policy_id, "source_path": source, "reason": reason})
    return output


def _gate_outcomes(route_id: str, work_kind: str, structured: dict[str, Any], observed: list[dict[str, Any]]) -> list[dict[str, str]]:
    contract = _yaml(ROOT / f"Orchestration/Contracts/TaskContracts/{route_id}.yaml")
    required = {str(item) for item in contract.get("required_quality_gates") or []}
    conditional = {str(item) for item in contract.get("conditional_quality_gates") or []}
    trusted: dict[str, dict[str, str]] = {}
    for item in observed:
        gate = str(item.get("gate") or "")
        status = str(item.get("status") or "")
        if gate and status in {"passed", "failed", "unavailable"}:
            trusted[gate] = {
                "id": gate,
                "requirement": "required",
                "status": status,
                "evidence": str(item.get("statement") or item.get("id") or "trusted fixture evidence"),
            }
    verification_scope = work_kind == "verification" and bool(trusted)
    effective_required = set(trusted) if verification_scope else required
    by_id: dict[str, dict[str, str]] = {}
    for item in structured.get("quality_gates") or []:
        if not isinstance(item, dict):
            continue
        gate = str(item.get("id") or "").strip()
        status = str(item.get("status") or "").strip()
        if not gate or status not in {"passed", "failed", "unavailable"}:
            continue
        if gate in effective_required:
            requirement = "required"
        elif verification_scope and gate in (required | conditional):
            requirement = "not_applicable"
        elif gate in conditional:
            requirement = "conditional"
        else:
            requirement = "informational"
        by_id[gate] = {
            "id": gate,
            "requirement": requirement,
            "status": status,
            "evidence": str(item.get("evidence") or ""),
        }
    by_id.update(trusted)
    for gate in effective_required:
        if gate not in by_id:
            by_id[gate] = {
                "id": gate,
                "requirement": "required",
                "status": "unavailable",
                "evidence": "Required gate was not observed in this attempt.",
            }
    return [by_id[key] for key in sorted(by_id)]


def _diff(before_root: Path, after_root: Path, changed: list[str]) -> str:
    chunks: list[str] = []
    for relative in changed:
        before = before_root / relative
        after = after_root / relative
        old = before.read_text(encoding="utf-8", errors="replace").splitlines(True) if before.is_file() else []
        new = after.read_text(encoding="utf-8", errors="replace").splitlines(True) if after.is_file() else []
        chunks.append(f"diff --git a/{relative} b/{relative}\n")
        chunks.extend(difflib.unified_diff(old, new, fromfile=f"a/{relative}", tofile=f"b/{relative}"))
    return "".join(chunks)


def _deterministic_mutation_evidence(workspace: Path, case_dir: Path, changed: list[str], allowed_paths: list[str]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    if changed and set(changed).issubset(set(allowed_paths)):
        evidence.append({
            "id": "runtime-mutation-scope",
            "gate": "static_review",
            "status": "passed",
            "source": "Runtime/Guardrails/mutation_guard.py",
            "scope": ",".join(changed),
            "statement": "Runtime mutation guard observed only explicitly allowed changed paths.",
        })
    dotnet = shutil.which("dotnet")
    if not dotnet:
        evidence.append({
            "id": "dotnet-compile",
            "gate": "compile",
            "status": "unavailable",
            "source": "one-repo-smoke",
            "scope": ",".join(changed),
            "statement": "dotnet CLI is unavailable in the Production Smoke environment.",
        })
        return evidence
    compile_dir = case_dir / "compile-check"
    compile_dir.mkdir(parents=True, exist_ok=False)
    sources = sorted(workspace.rglob("*.cs"))
    for source in sources:
        relative = source.relative_to(workspace)
        target = compile_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    includes = "\n".join(
        f'    <Compile Include="{xml.sax.saxutils.escape(source.relative_to(compile_dir).as_posix())}" />'
        for source in sorted(compile_dir.rglob("*.cs"))
    )
    project = compile_dir / "SmokeCompile.csproj"
    project.write_text(
        "<Project Sdk=\"Microsoft.NET.Sdk\">\n"
        "  <PropertyGroup>\n"
        "    <TargetFramework>net8.0</TargetFramework>\n"
        "    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>\n"
        "    <Nullable>enable</Nullable>\n"
        "  </PropertyGroup>\n"
        "  <ItemGroup>\n"
        f"{includes}\n"
        "  </ItemGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [dotnet, "build", str(project), "--nologo", "--verbosity", "minimal"],
        cwd=compile_dir,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    log = (completed.stdout or "") + (completed.stderr or "")
    (case_dir / "compile-evidence.txt").write_text(log, encoding="utf-8")
    evidence.append({
        "id": "dotnet-compile",
        "gate": "compile",
        "status": "passed" if completed.returncode == 0 else "failed",
        "source": "dotnet build",
        "scope": ",".join(source.relative_to(workspace).as_posix() for source in sources),
        "statement": f"dotnet build exited with code {completed.returncode}.",
    })
    return evidence


def _artifact_index(workspace: Path, case_dir: Path) -> None:
    artifacts: list[dict[str, str]] = []
    artifact_root = case_dir / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    for source in sorted(workspace.rglob("*.cs")):
        relative = source.relative_to(workspace).as_posix()
        dest = artifact_root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        artifacts.append({"path": dest.relative_to(case_dir).as_posix(), "language": "csharp", "kind": "source"})
    (case_dir / "artifact-index.yaml").write_text(
        yaml.safe_dump({"schema_version": "1.0", "artifacts": artifacts}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _persist_execution(case_dir: Path, result: dict[str, Any]) -> str:
    source = case_dir / "runtime/execution-result.yaml"
    digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    runtime_record = {
        "evidence_id": f"{result['run_id']}-execution-result",
        "run_id": result["run_id"],
        "step_id": result["step_id"],
        "producer": "Runtime/Runner/Codex/codex_runner.py",
        "source_type": "runtime_execution_result",
        "source_ref": source.relative_to(case_dir).as_posix(),
        "payload_ref": source.relative_to(case_dir).as_posix(),
        "hash": digest,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provenance": ["Runtime/Runner/Codex/codex_runner.py", "Operations/ProductionSmoke/run_one_repo_smoke.py"],
        "definition_fingerprint": result["definition_fingerprint"],
        "status": "passed" if result.get("status") == "passed" else "failed",
    }
    durable = from_runtime_execution_evidence(runtime_record)
    EvidenceStore(case_dir / "persistence").append(durable)
    return durable["evidence_id"]


def _context_manifest(route_id: str, fingerprint: dict[str, str], view: dict[str, Any], policies: list[dict[str, str]], gates: list[dict[str, str]], observed: list[dict[str, Any]]) -> dict[str, Any]:
    execution_evidence = [
        {"gate": str(item.get("gate") or ""), "status": str(item.get("status") or ""), "source": str(item.get("source") or "fixture"), "statement": str(item.get("statement") or "")}
        for item in observed if isinstance(item, dict)
    ]
    return {
        "schema_version": "1.0",
        "task": {"route": route_id, "fingerprint": fingerprint},
        "policy": {"loaded": policies},
        "knowledge": {"loaded": []},
        "harness": {"quality_gates": gates},
        "execution": {"unresolved_bindings": view.get("unresolved_bindings") or [], "evidence": execution_evidence},
        "context": {
            "context_id": view["context_id"],
            "context_fingerprint": view["context_fingerprint"],
            "definition_fingerprint": view["definition_fingerprint"],
        },
    }


def _envelope(case_run_id: str, task_id: str, runtime_result: dict[str, Any], gates: list[dict[str, str]], evidence_id: str, protocol_error: str | None) -> dict[str, Any]:
    failure_class = None
    status = "completed"
    if runtime_result.get("runtime_failure"):
        failure_class = str(runtime_result["runtime_failure"].get("failure_class") or "runtime_protocol_failure")
        status = "failed"
    elif protocol_error:
        failure_class = "agent_behavior_regression"
        status = "failed"
    else:
        blocking = [gate for gate in gates if gate.get("requirement") == "required"]
        if any(gate.get("status") == "failed" for gate in blocking):
            status = "failed"
            failure_class = "agent_behavior_regression"
        elif any(gate.get("status") == "unavailable" for gate in blocking):
            status = "unavailable"
    return {
        "schema_version": "1.0",
        "run_id": case_run_id,
        "golden_task_id": task_id,
        "status": status,
        "failure_class": failure_class,
        "attempt": {"agent_attempt": 1},
        "execution_owner": {"repository": "DarumaPPAP/UnityAgent", "component": "Runtime/Runner/Codex"},
        "runtime": runtime_result.get("tool_identity") or {},
        "execution_fingerprint": runtime_result.get("definition_fingerprint") or {},
        "evidence": {
            "context_manifest": "context-manifest.yaml",
            "response": "response.md",
            "artifact_index": "artifact-index.yaml",
            "diff": "diff.patch",
            "gate_evidence": gates,
            "persistence_evidence": evidence_id,
        },
    }


def _case_config(suite: dict[str, Any], contracts: dict[str, Any], only_case: str | None) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    production = contracts.get("cases") or {}
    output = []
    for suite_case in suite.get("cases") or []:
        task_id = str(suite_case.get("golden_task_id") or "")
        if only_case and task_id != only_case:
            continue
        contract = production.get(task_id)
        if not isinstance(contract, dict):
            raise ProductionSmokeError(f"missing Production Smoke contract: {task_id}")
        output.append((suite_case, contract))
    if only_case and not output:
        raise ProductionSmokeError(f"unknown Production Smoke case: {only_case}")
    return output


def run_case(base_run_id: str, suite_case: dict[str, Any], contract: dict[str, Any], *, model: str, timeout_seconds: float, reasoning_effort: str, command_json: str | None) -> dict[str, Any]:
    task_id = str(suite_case["golden_task_id"])
    case_run_id = f"{base_run_id}-{task_id.lower()}"
    case_dir = DEFAULT_ROOT / base_run_id / task_id
    fixture_rel = canonicalize_repo_path(str(suite_case["workspace_fixture"]))
    fixture = (ROOT / fixture_rel).resolve()
    if not fixture.is_dir():
        raise ProductionSmokeError(f"fixture missing: {fixture_rel}")
    workspace = case_dir / "workspace"
    original = case_dir / "workspace-before"
    if case_dir.exists():
        raise ProductionSmokeError(f"immutable case output already exists: {case_dir}")
    workspace.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(fixture, workspace)
    shutil.copytree(fixture, original)

    production_prompt = str(contract.get("production_prompt") or "").strip()
    observed = list(contract.get("observed_evidence") or [])
    allowed_paths = [str(item) for item in suite_case.get("allowed_paths") or []]
    fingerprint = _fingerprint(production_prompt, str(suite_case["work_kind"]), allowed_paths, observed)
    route_decision = select_route(fingerprint, load_routes(ROUTES))
    route_id = str(route_decision["route_id"])
    view = materialize_context(case_run_id, route_id, bindings=_bindings(route_id, production_prompt, workspace, allowed_paths), root=ROOT)
    runtime_work_kind = _runtime_work_kind(str(suite_case["work_kind"]))
    request = {
        "schema_version": "1.0",
        "run_id": case_run_id,
        "step_id": "production-smoke",
        "action_id": f"{route_id}:production-smoke",
        "workspace_root": str(workspace),
        "prompt": _prompt(production_prompt, view),
        "definition_fingerprint": view["definition_fingerprint"],
        "execution": {
            "profile": str(route_decision["profile"]),
            "work_kind": runtime_work_kind,
            "mutation_authorized": runtime_work_kind == "mutation",
            "human_approval_required": False,
            "human_approval_granted": False,
        },
        "tool_identity": {"provider": "openai", "model": model, "execution_mode": "one-repo-production-smoke"},
        "mutation_scope": {
            "allowed_paths": allowed_paths,
            "prohibited_paths": [str(item) for item in suite_case.get("prohibited_paths") or []],
        },
        "gate_outcomes": [],
    }
    request_path = case_dir / "runtime-request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    runtime_dir = case_dir / "runtime"
    command = [
        sys.executable, str(RUNTIME), "--request", str(request_path), "--output", str(runtime_dir),
        "--timeout-seconds", str(timeout_seconds), "--reasoning-effort", reasoning_effort,
    ]
    if command_json:
        tokens = json.loads(command_json)
        if not isinstance(tokens, list) or not tokens or not all(isinstance(item, str) and item for item in tokens):
            raise ProductionSmokeError("--command-json must be a non-empty JSON string array")
        if any(any(marker in token.replace("\\", "/").lower() for marker in FAKE_MARKERS) for token in tokens):
            raise ProductionSmokeError("real Production Smoke refuses fake Codex/Production Agent fixtures")
        command.extend(["--command-json", json.dumps(tokens)])
    completed = subprocess.run(command, cwd=ROOT, check=False)
    result_path = runtime_dir / "execution-result.yaml"
    if not result_path.is_file():
        raise ProductionSmokeError(f"Runtime did not produce execution-result.yaml for {task_id}")
    runtime_result = _yaml(result_path)
    evidence_id = _persist_execution(case_dir, runtime_result)

    response_path = runtime_dir / "response.md"
    if response_path.is_file():
        shutil.copy2(response_path, case_dir / "response.md")
    else:
        (case_dir / "response.md").write_text("", encoding="utf-8")
    structured = None
    protocol_error = None
    policies: list[dict[str, str]] = []
    gates: list[dict[str, str]] = []
    if runtime_result.get("status") == "passed":
        try:
            structured = _parse_response(case_dir / "response.md")
            policies = _validated_policies(structured)
            gates = _gate_outcomes(route_id, runtime_work_kind, structured, observed)
        except ProductionSmokeError as exc:
            protocol_error = str(exc)
    else:
        gates = _gate_outcomes(route_id, runtime_work_kind, {"quality_gates": []}, observed)

    changed_obj = runtime_result.get("changed_paths") or {}
    changed = list(changed_obj.get("paths") or []) if changed_obj.get("observation_state") == "observed" else []
    if runtime_work_kind == "mutation" and runtime_result.get("status") == "passed":
        observed.extend(_deterministic_mutation_evidence(workspace, case_dir, changed, allowed_paths))
        if structured is not None:
            gates = _gate_outcomes(route_id, runtime_work_kind, structured, observed)
    (case_dir / "diff.patch").write_text(_diff(original, workspace, changed), encoding="utf-8")
    _artifact_index(workspace, case_dir)
    (case_dir / "context-manifest.yaml").write_text(
        yaml.safe_dump(_context_manifest(route_id, fingerprint, view, policies, gates, observed), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    envelope = _envelope(case_run_id, task_id, runtime_result, gates, evidence_id, protocol_error)
    (case_dir / "execution-envelope.yaml").write_text(yaml.safe_dump(envelope, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {
        "task_id": task_id,
        "run_id": case_run_id,
        "route": route_id,
        "profile": route_decision["profile"],
        "runtime_status": runtime_result.get("status"),
        "envelope_status": envelope["status"],
        "changed_paths": changed_obj,
        "protocol_error": protocol_error,
        "persistence_evidence_id": evidence_id,
        "case_dir": case_dir.relative_to(ROOT).as_posix(),
        "runtime_exit": completed.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--case")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh"), default="high")
    parser.add_argument("--command-json")
    args = parser.parse_args()
    try:
        if args.timeout_seconds <= 30:
            raise ProductionSmokeError("timeout must be greater than 30 seconds")
        run_id = _safe_run_id(args.run_id)
        run_root = DEFAULT_ROOT / run_id
        if run_root.exists():
            raise ProductionSmokeError(f"immutable run root already exists: {run_root}")
        suite = (_yaml(SUITES).get("suites") or {}).get("production_smoke") or {}
        contracts = _yaml(CONTRACTS)
        results = [
            run_case(run_id, suite_case, contract, model=args.model, timeout_seconds=args.timeout_seconds,
                     reasoning_effort=args.reasoning_effort, command_json=args.command_json)
            for suite_case, contract in _case_config(suite, contracts, args.case)
        ]
        summary = {
            "schema_version": "1.0", "run_id": run_id,
            "execution_repository": "DarumaPPAP/UnityAgent", "production_execution_required": True,
            "cases": results,
        }
        (run_root / "execution-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if all(item["envelope_status"] == "completed" for item in results) else 10
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"One-repo Production Smoke setup/execution failed: {exc}", file=sys.stderr)
        return 30


if __name__ == "__main__":
    raise SystemExit(main())
