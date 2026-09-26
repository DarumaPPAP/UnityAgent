#!/usr/bin/env python3
"""Run a live Codex reasoning smoke with a disposable Unity-shaped project."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Context.Manifest.build_context_manifest import build as build_context_manifest
from Context.Selection.project_context_inputs import derive_context_inputs
from Orchestration.Orchestrator.orchestrator import runtime_handoff
from Orchestration.Routing.route_selector import load_routes, resolve_specialist, select_route, select_specialist_capability, task_fingerprint_from_intent
from Orchestration.ToolRouting.capability_request_builder import build_candidate_capability_requests, build_capability_requests, conditions_for_intent, task_contract_projection
from Runtime.Contracts.reasoning_output import verify_reasoning_artifact
from Runtime.Handoff.reasoning_runtime import execute_reasoning
from Runtime.ReferenceImplementation.candidate_profiles import load_candidate_profile
from Runtime.ReferenceImplementation.world_planning import WorldPlanContractError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    version = subprocess.run(["codex", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="unityagent-world-smoke-") as temporary:
        base = Path(temporary)
        project = base / "Project"
        for folder in ("Assets", "Packages", "ProjectSettings"):
            (project / folder).mkdir(parents=True)
        (project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.15f1\n", encoding="utf-8")
        intent = {"kind": "world_planning", "world_goal": "Plan a small dungeon with an entrance, two rooms and an exit", "scene_scope": "Assets/Scenes/Dungeon", "prohibited_changes": ["Do not change player spawn"]}
        snapshot = {"project": {"root": str(project), "exists": True, "identity_status": "bound", "unity_version": "6000.3.15f1"}, "filesystem": {"readable": True}, "build": {"requested_target": "unknown"}}
        task = task_fingerprint_from_intent(intent, snapshot, project_root=str(project), policy_allowed=True)
        route = select_route(task, load_routes(ROOT / "Orchestration/Routing/task-routes.yaml"))
        conditions = conditions_for_intent(intent, task)
        production = build_capability_requests(route_id=route["route_id"], project_root=str(project), active_conditions=conditions)
        candidate = build_candidate_capability_requests(route["route_id"], str(project), active_conditions=conditions)
        capability = select_specialist_capability(route["route_id"], production + candidate)
        inputs = derive_context_inputs(str(project), snapshot, intent)
        selection = resolve_specialist(route["route_id"], capability, snapshot, pilot_enabled=True, context_items=inputs["specialist_items"])
        manifest = build_context_manifest("run-world-smoke", route["route_id"], project_facts=inputs["project_facts"], bindings=inputs["bindings"], capability_ids=[item["capability"] for item in production], active_conditions=conditions, specialist_selection=selection, specialist_items=inputs["specialist_items"], specialist_tags=inputs["specialist_tags"], required_specialist_keys=inputs["required_specialist_keys"])
        view = manifest["materialized_context"]
        profile = load_candidate_profile(selection["profile_id"])
        revisions = {name: "live-smoke" for name in ("architecture_version", "policy_revision", "prompt_revision", "context_revision", "graph_revision", "runtime_profile_revision", "tool_schema_revision", "checkpoint_schema_revision", "evidence_schema_revision", "eval_contract_revision")}
        revisions["policy_revision"] = view["definition_fingerprint"]["policy_revision"]
        revisions["context_revision"] = view["definition_fingerprint"]["context_revision"]
        action = {"kind": "specialist_reasoning", "profile_id": profile["profile_id"], "capability": capability, "execution_mode": profile["execution_mode"], "provider_resolution": profile["provider_resolution"], "output_contract_ref": profile["output_contract_ref"], "instructions_ref": profile["instructions_ref"]}
        handoff = runtime_handoff(run_id="run-world-smoke", node_id="inspect_sources", route_id=route["route_id"], execution_profile="generic_planning", context_id=view["context_id"], context_fingerprint=view["context_fingerprint"]["value"], task_contract_runtime_projection=task_contract_projection(route["route_id"]), mutation_scope={}, validation_requirements=["world_plan"], capability_requests=production, runtime_action=action, definition_fingerprint={"schema_version": "1.0", **revisions})
        output = base / "reasoning-output"
        execution, artifact = execute_reasoning(handoff, manifest, original_project=project, output=output, model=args.model, timeout_seconds=args.timeout_seconds)
        provenance = execution.get("reasoning_provenance") or {}
        report = {"codex_version": version, "model": args.model, "model_provider": provenance.get("model_provider"), "model_revision": provenance.get("model_revision"), "reasoning_effort": provenance.get("reasoning_effort"), "runtime_profile": "generic_planning", "sandbox_mode": execution.get("sandbox_mode"), "output_schema_used": True, "context_fingerprint": view["context_fingerprint"]["value"], "original_project_changed_paths": execution.get("original_workspace_changed_paths"), "structured_output_artifact": execution.get("structured_output_ref"), "runtime_status": execution["status"], "runtime_failure": execution.get("runtime_failure"), "semantic_status": None}
        if artifact is not None:
            try:
                report["semantic_status"] = verify_reasoning_artifact(action["output_contract_ref"], manifest, artifact)["status"]
            except WorldPlanContractError as exc:
                report["semantic_status"] = "failed"
                report["semantic_failure"] = str(exc)
                report["open_decisions"] = artifact.get("world_plan", {}).get("open_decisions")
                report["platform_constraints"] = artifact.get("world_plan", {}).get("platform_constraints")
        if args.evidence_dir:
            evidence_dir = args.evidence_dir.expanduser().resolve()
            if evidence_dir.exists():
                raise ValueError(f"evidence directory already exists: {evidence_dir}")
            evidence_dir.mkdir(parents=True)
            shutil.copytree(output, evidence_dir / "runtime")
            (evidence_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report["evidence_dir"] = str(evidence_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if execution["status"] != "passed" or report["semantic_status"] != "runtime_contract_verified":
            for name in ("codex-stderr.txt", "codex-events.jsonl"):
                source = output / name
                if source.is_file():
                    print(f"{name}: {source.read_text(encoding='utf-8')[-3000:]}", file=sys.stderr)
            return 10
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
