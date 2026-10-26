#!/usr/bin/env python3
"""Small host entrypoint for UnityAgent Control Plane setup operations."""
from __future__ import annotations
from unityagent.resources import resource_root

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = resource_root()

from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.control_plane.full_e2e import apply_full_e2e, approve_full_e2e, approve_full_e2e_save, plan_full_e2e
from unityagent.persistence.store.atomic_store import PersistenceError, read_json, safe_id
from unityagent.runtime.tooling.providers.installer.installer_provider import InstallerProvider
from unityagent.runtime.reference_implementation.profiles import runtime_profile_revision
from unityagent.control_plane.unity_agent_control_plane import validate_entry_request
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.environment.project_identity import resolve_project_root, same_project_root
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider

PRODUCTS = (
    "official_unity_cli",
    "artist_subagent",
    "codex_cli",
    "unity_agent_codex_plugin",
    "blender_mcp",
    "unity_cli_loop",
)
CHANNEL = "0.0.8-beta"


def _fingerprint() -> dict[str, str]:
    def digest(relative: str) -> str:
        path = ROOT / relative
        try:
            return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        except OSError:
            return "missing:" + relative

    return {
        "schema_version": "1.0",
        "architecture_version": digest("src/unityagent/contracts/unityagent-layer-contract.yaml"),
        "policy_revision": digest("src/unityagent/policy/user/user-policy.yaml"),
        "prompt_revision": digest("src/unityagent/context/prompt/templates/01_optimize_from_audit.md"),
        "context_revision": digest("src/unityagent/context/selection/context-catalog.yaml"),
        "graph_revision": digest("src/unityagent/orchestration/definitions/development-parent-graph.yaml"),
        "runtime_profile_revision": runtime_profile_revision(root=ROOT),
        "tool_schema_revision": digest("src/unityagent/runtime/contracts/toolchain-setup-request.schema.yaml"),
        "checkpoint_schema_revision": digest("src/unityagent/persistence/contracts/run-checkpoint.schema.yaml"),
        "evidence_schema_revision": digest("src/unityagent/persistence/contracts/evidence-record.schema.yaml"),
        "eval_contract_revision": digest("eval/datasets/behavior/production-tool-runtime-environment-matrix.yaml"),
    }


def _default_state_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local")
        return Path(base) / "UnityAgent"
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local/state")
    return Path(base) / "unityagent"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="uagent", description="UnityAgent Control Plane host", allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    artist = subparsers.add_parser("artist", help="Artistの型付き操作・Plan明示承認を既存Control Planeへ渡す")
    artist.add_argument("artist_command", choices=("inspect", "plan", "preview", "apply", "capture", "evaluate", "refine", "history", "cinematic", "approve"))
    _add_project_arguments(artist)
    artist.add_argument("--state-root", type=Path, default=_default_state_root())
    artist.add_argument("--run-id", required=True)
    artist.add_argument("--domain", choices=("visual_art", "cinematic"))
    artist_input = artist.add_mutually_exclusive_group()
    artist_input.add_argument("--request-json")
    artist_input.add_argument("--request-file", type=Path)
    artist.add_argument("--plan-id")
    artist.add_argument("--expected-revision")
    artist.add_argument("--capture-id")
    artist.add_argument("--decision", choices=("accepted", "rejected", "needs_refine"))
    artist.add_argument("--notes")
    artist.add_argument("--evaluation-id")
    artist.add_argument("--operation", dest="cinematic_operation", choices=("inspect", "plan", "preview", "apply"))
    artist.add_argument("--approval-ref")
    artist.add_argument("--expires-at")
    artist.add_argument("--allowed-path", action="append", dest="allowed_paths")
    artist.add_argument("--prohibited-path", action="append", dest="prohibited_paths")
    artist.add_argument("--timeout-seconds", type=float, default=120.0)
    hot = subparsers.add_parser("hot-reload", help="Optional CLI Loop V3; 通常Compile/QAは別Gate")
    hot.add_argument("operation", choices=("plan", "approve", "apply"))
    _add_project_arguments(hot)
    hot.add_argument("--state-root", type=Path, default=_default_state_root())
    hot.add_argument("--file", action="append", default=[])
    hot.add_argument("--runner-path", type=Path)
    hot.add_argument("--runner-sha256")
    hot.add_argument("--plan-id")
    hot.add_argument("--approval-ref")
    rock = subparsers.add_parser("rock", help="承認済み固定TemplateによるBlender MCP岩制作")
    rock.add_argument("operation", choices=("plan", "approve", "apply"))
    _add_project_arguments(rock)
    rock.add_argument("--state-root", type=Path, default=_default_state_root())
    rock.add_argument("--job-id", default="rock-g1")
    rock.add_argument("--plan-id")
    rock.add_argument("--approval-ref")
    rock.add_argument("--mcp-executable", type=Path)
    rock_import = subparsers.add_parser("rock-import", help="承認済みFBXのProduction Editor Import/復旧")
    rock_import.add_argument("operation", choices=("plan", "approve", "apply", "rollback"))
    _add_project_arguments(rock_import)
    rock_import.add_argument("--state-root", type=Path, default=_default_state_root())
    rock_import.add_argument("--job-id", default="rock-g1")
    rock_import.add_argument("--plan-id")
    rock_import.add_argument("--kind", choices=("mutation", "save", "rollback"))
    rock_import.add_argument("--approval-ref")
    rock_import.add_argument("--save-approval-ref")
    rock_import.add_argument("--rollback-approval-ref")
    e2e = subparsers.add_parser("e2e", help="固定のUnity Editor Full E2E検証")
    e2e.add_argument("operation", choices=("plan", "approve", "approve-save", "apply"))
    _add_project_arguments(e2e)
    e2e.add_argument("--state-root", type=Path, default=_default_state_root())
    e2e.add_argument("--plan-id")
    e2e.add_argument("--approval-ref")
    e2e.add_argument("--save-approval-ref")
    e2e.add_argument("--timeout-seconds", type=float, default=180.0)
    run_parser = subparsers.add_parser("run", help="Entry v2からRead-only TaskをControl Planeへ渡す")
    run_parser.add_argument("--request", type=Path, required=True)
    run_parser.add_argument("--state-root", type=Path, default=_default_state_root())
    run_parser.add_argument("--reasoning-model")
    run_parser.add_argument("--reasoning-effort", default="high")
    for command in ("doctor", "setup"):
        subparser = subparsers.add_parser(command)
        if command == "setup":
            subparser.add_argument("setup_operation", nargs="?", choices=("plan", "apply"))
        subparser.add_argument("--operation", choices=("doctor", "plan", "apply"))
        _add_project_arguments(subparser)
        subparser.add_argument("--product", action="append", choices=PRODUCTS, dest="products")
        subparser.add_argument("--channel", default=CHANNEL)
        subparser.add_argument("--entry-point", choices=("unity_ui", "codex_plugin"), default="codex_plugin")
        subparser.add_argument("--approval-ref")
        subparser.add_argument("--expected-plan-id")
        subparser.add_argument("--approved-plan", type=Path)
        subparser.add_argument("--install-root", type=Path)
        subparser.add_argument("--codex-path", type=Path)
        subparser.add_argument("--state-root", type=Path, default=_default_state_root())
        subparser.add_argument("--format", choices=("json",), default="json")
        subparser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()
    if args.command in {"doctor", "setup"}:
        positional = getattr(args, "setup_operation", None)
        if positional is not None and args.operation is not None:
            parser.error("setup operation must be supplied either positionally or with --operation")
        args.operation = positional or args.operation or ("doctor" if args.command == "doctor" else "plan")
    if args.command != "run":
        try:
            args.project_path = resolve_project_root(args.project_path)
        except (ValueError, OSError, RuntimeError) as exc:
            parser.error(str(exc))
    return args


def _add_project_arguments(parser: argparse.ArgumentParser) -> None:
    parser.allow_abbrev = False
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--project-p", dest="project_path", help="Unity Project root (default: nearest parent of CWD)")
    group.add_argument("--project-path", dest="project_path", help="Compatibility alias for --project-p")


def _require_plan_project(args: argparse.Namespace) -> None:
    if args.operation == "plan":
        return
    directories = {"hot-reload": "hot-reload-plans", "rock": "rock-plans", "rock-import": "rock-import/plans"}
    plan_path = args.state_root.expanduser().resolve() / directories[args.command] / (safe_id(args.plan_id) + ".json")
    plan = read_json(plan_path)
    # 保存済みPlanのProjectへ暗黙に切り替えず、CLIで解決した対象との一致を要求する。
    root = plan.get("project_root")
    if not isinstance(root, str) or not root.strip() or not same_project_root(root, args.project_path):
        raise ValueError("Project does not match the reviewed Plan")


def main() -> int:
    args = _parse_args()
    if args.command == "artist":
        from unityagent.control_plane.artist_execution import execute_artist, approve_artist_execution
        from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand
        try:
            plane = UnityAgentControlPlane(args.state_root)
            if args.artist_command == "approve":
                if not args.plan_id:
                    raise ValueError("Artist approve requires --plan-id")
                result = {"status": "approved", **approve_artist_execution(plane, args.project_path, args.run_id, args.plan_id, expires_at=args.expires_at)}
            else:
                if args.expires_at:
                    raise ValueError("--expires-at is only valid for explicit Artist approve")
                payload = args.request_file.read_text(encoding="utf-8") if args.request_file is not None else args.request_json
                command = ArtistCommand(args.artist_command, request_json=payload, plan_id=args.plan_id, expected_revision=args.expected_revision, capture_id=args.capture_id, decision=args.decision, notes=args.notes, evaluation_id=args.evaluation_id, operation=args.cinematic_operation)
                scope = {"allowed_paths": args.allowed_paths or ["Assets"], "prohibited_paths": args.prohibited_paths if args.prohibited_paths is not None else ["Packages", "ProjectSettings"]} if args.allowed_paths is not None or args.prohibited_paths is not None else None
                result = execute_artist(plane, args.project_path, args.run_id, command, definition_fingerprint=_fingerprint(), scope=scope, approval_ref=args.approval_ref, timeout_seconds=args.timeout_seconds, domain=args.domain)
        except (ValueError, OSError, PersistenceError) as exc:
            result = {"status": "blocked", "reason": str(exc), "gate": "BLOCKED_NOT_RUN"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") in {"completed", "planned", "approved"} else 1
    if args.command == "hot-reload":
        from unityagent.control_plane.hot_reload import plan_hot_reload, approve_hot_reload, apply_hot_reload
        try:
            _require_plan_project(args)
            if args.operation == "plan":
                if not args.runner_path or not args.runner_sha256:
                    raise ValueError("A reviewed installed project runner path and SHA-256 are required; setup is explicit")
                result = {"status":"planned", **plan_hot_reload(args.project_path,args.state_root,
                    args.file,args.runner_path,args.runner_sha256,_fingerprint())}
            elif args.operation == "approve":
                result = {"status":"approved", **approve_hot_reload(args.state_root,args.plan_id or "")}
            else:
                result = apply_hot_reload(UnityAgentControlPlane(args.state_root),args.plan_id or "",args.approval_ref or "", definition_fingerprint=_fingerprint())
        except (ValueError, OSError, PersistenceError) as exc:
            result = {"status":"blocked","reason":str(exc),"gate":"BLOCKED_NOT_RUN"}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result["status"] in {"planned","approved"} or result.get("acceptance") == "verified" else 1
    if args.command == "rock-import":
        from unityagent.control_plane.rock_import import (
            plan_rock_import, approve_rock_import, apply_rock_import, rollback_rock_import)
        try:
            _require_plan_project(args)
            if args.operation == "plan":
                result = {"status":"planned", **plan_rock_import(args.project_path,args.state_root,
                    args.job_id,_fingerprint())}
            elif args.operation == "approve":
                decision = approve_rock_import(args.state_root,args.plan_id or "",args.kind or "")
                result = {"status":"approved",**decision}
            elif args.operation == "apply":
                result = apply_rock_import(UnityAgentControlPlane(args.state_root),args.plan_id or "",
                    args.approval_ref or "",args.save_approval_ref or "",
                    definition_fingerprint=_fingerprint())
            else:
                result = rollback_rock_import(UnityAgentControlPlane(args.state_root),
                    args.plan_id or "",args.rollback_approval_ref or "",
                    definition_fingerprint=_fingerprint())
        except (ValueError, OSError, PersistenceError) as exc:
            result = {"status":"blocked","reason":str(exc),"gate":"BLOCKED_NOT_RUN"}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result.get("status") in {"planned","approved","completed"} else 1
    if args.command == "rock":
        from unityagent.control_plane.rock_artifact import plan_rock, approve_rock, apply_rock
        from unityagent.runtime.tooling.providers.blender_mcp.stdio_client import McpStdioClient
        import shutil
        try:
            _require_plan_project(args)
            if args.operation == "plan":
                result = {"status": "planned", **plan_rock(args.project_path, args.state_root, args.job_id, _fingerprint())}
            elif args.operation == "approve":
                result = {"status": "approved", **approve_rock(args.state_root, args.plan_id or "")}
            else:
                executable = str(args.mcp_executable) if args.mcp_executable else shutil.which("blender-mcp")
                if not executable or not Path(executable).is_file():
                    raise ValueError("Blender MCP server unavailable; installation requires explicit setup approval")
                with McpStdioClient([executable]) as client:
                    result = apply_rock(UnityAgentControlPlane(args.state_root), args.plan_id or "",
                        args.approval_ref or "", client, definition_fingerprint=_fingerprint())
        except (ValueError, OSError, PersistenceError) as exc:
            result = {"status": "blocked", "reason": str(exc), "gate": "BLOCKED_NOT_RUN"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"planned", "approved", "completed"} else 1
    if args.command == "e2e":
        try:
            if args.operation == "plan":
                result = plan_full_e2e(args.project_path, args.state_root)
            elif args.operation == "approve":
                result = approve_full_e2e(args.project_path, args.state_root, args.plan_id or "")
            elif args.operation == "approve-save":
                result = approve_full_e2e_save(args.project_path, args.state_root, args.plan_id or "")
            else:
                if not 1 <= args.timeout_seconds <= 900:
                    raise ValueError("E2E timeout must be between 1 and 900 seconds")
                result = apply_full_e2e(
                    args.project_path,
                    args.state_root,
                    args.plan_id or "",
                    args.approval_ref or "",
                    args.save_approval_ref or "",
                    definition_fingerprint=_fingerprint(),
                    timeout_seconds=args.timeout_seconds,
                )
        except (ValueError, OSError, PersistenceError) as exc:
            result = {"status": "blocked", "reason": str(exc)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"planned", "approved", "completed"} else 1
    if args.command == "run":
        request = json.loads(args.request.read_text(encoding="utf-8"))
        validate_entry_request(request)
        project_root = request["project_root"]
        snapshot = discover_environment(project_root)
        file_provider = FileProvider(project_root)
        source_scope = request.get("intent", {}).get("target_scope")
        definition = _fingerprint()
        definition["tool_schema_revision"] = "sha256:" + hashlib.sha256((ROOT / "src/unityagent/runtime/contracts/capability-request.schema.yaml").read_bytes()).hexdigest()
        result = UnityAgentControlPlane(args.state_root).execute(request, environment_snapshot=snapshot, context=ResolutionContext(policy_allowed=True), executors={"file": file_provider.execute}, provider_arguments={"file": {"relative_path": source_scope}}, definition_fingerprint=definition, reasoning_model=args.reasoning_model, reasoning_effort=args.reasoning_effort)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        # Control Planeの未完了をCLI成功へ昇格しない。
        return 0 if result["status"] == "completed" else 1
    if args.channel != CHANNEL:
        raise SystemExit(f"only the {CHANNEL} setup channel is supported")
    project_root = Path(args.project_path).expanduser().resolve(strict=False)
    products = args.products or ["official_unity_cli"]
    request = {
        "schema_version": "1.0",
        "request_id": f"{args.command}-{os.getpid()}",
        "operation": args.operation,
        "project_root": str(project_root),
        "products": products,
        "channel": args.channel,
        "non_interactive": bool(args.non_interactive),
        "approval_ref": args.approval_ref,
        "expected_plan_id": args.expected_plan_id,
        "install_root": None if args.install_root is None else str(args.install_root.expanduser().resolve(strict=False)),
        "codex_cli_path": None if args.codex_path is None else str(args.codex_path.expanduser().resolve(strict=False)),
    }
    approved_plan = None
    if args.approved_plan:
        approved_plan = json.loads(args.approved_plan.read_text(encoding="utf-8"))
        if isinstance(approved_plan, dict) and isinstance(approved_plan.get("outcome"), dict):
            approved_plan = approved_plan["outcome"].get("provider_result", approved_plan)
        if args.operation == "apply":
            root = approved_plan.get("project_root") if isinstance(approved_plan, dict) else None
            if not isinstance(root, str) or not root.strip() or not same_project_root(root, project_root):
                raise SystemExit("Project does not match the approved setup Plan")

    installer = InstallerProvider(project_root)
    plane = UnityAgentControlPlane(args.state_root)
    result = plane.setup(
        args.entry_point,
        request,
        executors={"installer": installer.execute},
        definition_fingerprint=_fingerprint(),
        executor_arguments={"approval_complete": bool(args.approval_ref), "approved_plan": approved_plan},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
