#!/usr/bin/env python3
"""Small host entrypoint for UnityAgent Control Plane setup operations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ControlPlane.unity_agent_control_plane import UnityAgentControlPlane
from Runtime.Tooling.Providers.Installer.installer_provider import InstallerProvider

PRODUCTS = (
    "official_unity_cli",
    "unity_artist_cli",
    "codex_cli",
    "unity_agent_codex_plugin",
)
CHANNEL = "0.0.5-beta"


def _fingerprint() -> dict[str, str]:
    def digest(relative: str) -> str:
        path = ROOT / relative
        try:
            return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        except OSError:
            return "missing:" + relative

    return {
        "schema_version": "1.0",
        "architecture_version": digest("Specs/unityagent-layer-contract.yaml"),
        "policy_revision": digest("Policy/User/user-policy.yaml"),
        "prompt_revision": digest("Prompt/01_optimize_from_audit.md"),
        "context_revision": digest("Context/Selection/context-catalog.yaml"),
        "graph_revision": digest("Orchestration/Definitions/development-parent-graph.yaml"),
        "runtime_profile_revision": digest("Runtime/Tooling/provider_registry.yaml"),
        "tool_schema_revision": digest("Runtime/Contracts/toolchain-setup-request.schema.yaml"),
        "checkpoint_schema_revision": digest("Persistence/Contracts/run-checkpoint.schema.yaml"),
        "evidence_schema_revision": digest("Persistence/Contracts/evidence-record.schema.yaml"),
        "eval_contract_revision": digest("Eval/Datasets/Behavior/production-tool-runtime-environment-matrix.yaml"),
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
