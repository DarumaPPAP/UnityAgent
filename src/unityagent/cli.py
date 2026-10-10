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
from unityagent.persistence.store.atomic_store import PersistenceError
from unityagent.runtime.tooling.providers.installer.installer_provider import InstallerProvider
from unityagent.runtime.reference_implementation.profiles import runtime_profile_revision
from unityagent.control_plane.unity_agent_control_plane import validate_entry_request
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.providers.file.file_provider import FileProvider

PRODUCTS = (
    "official_unity_cli",
    "unity_artist_cli",
    "codex_cli",
    "unity_agent_codex_plugin",
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
    parser = argparse.ArgumentParser(description="UnityAgent Control Plane host")
    subparsers = parser.add_subparsers(dest="command", required=True)
    e2e = subparsers.add_parser("e2e", help="固定のUnity Editor Full E2E検証")
    e2e.add_argument("operation", choices=("plan", "approve", "approve-save", "apply"))
    e2e.add_argument("--project-path", required=True)
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
        subparser.add_argument("--operation", choices=("doctor", "plan", "apply"), default=command if command == "doctor" else "plan")
        subparser.add_argument("--project-path", required=True)
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
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
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
    products = args.products or ["official_unity_cli", "unity_artist_cli"]
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
