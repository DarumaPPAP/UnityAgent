#!/usr/bin/env python3
"""Windows interactive Full E2E harness; the canonical Unity fixture stays in the repository."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import venv

ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATHS = (
    "src/unityagent",
    "Packages/com.darumappap.unity-agent",
    "tests/unity/projects/production-e2e",
    "tests/unity/verify/full_e2e_ci.py",
    "tests/unity/scripts/run-full-e2e.ps1",
)
EXPECTED_ASSETS = {
    "Assets/UnityAgentE2E.meta",
    "Assets/UnityAgentE2E/FullE2EScene.unity",
    "Assets/UnityAgentE2E/FullE2EScene.unity.meta",
    "Assets/UnityAgentE2E/FullE2EMaterial.mat",
    "Assets/UnityAgentE2E/FullE2EMaterial.mat.meta",
    "Assets/UnityAgentE2E/FullE2EProbe.cs",
    "Assets/UnityAgentE2E/FullE2EProbe.cs.meta",
}


def command(arguments: list[str], *, timeout: int = 120, output: Path | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False)
    if output:
        output.write_text(completed.stdout + "\n--- stderr ---\n" + completed.stderr, encoding="utf-8")
    return completed


def git_source_revision(repo: Path, expected: str | None) -> str:
    sha = command(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if sha.returncode != 0 or not re.fullmatch(r"[a-f0-9]{40}", sha.stdout.strip()):
        raise RuntimeError("Git HEAD could not be verified")
    actual = sha.stdout.strip()
    if expected and actual != expected:
        raise RuntimeError(f"Revision mismatch: expected {expected}, got {actual}")
    changes = command(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all", "--", *SOURCE_PATHS])
    if changes.returncode != 0 or changes.stdout.strip():
        raise RuntimeError("Fixture / UPM / Control Plane source is not clean: " + changes.stdout[:600])
    return actual


def reject_links(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"Fixture/package folder missing or linked: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"Linked fixture/package input rejected: {path}")


def prepare_workspace(repo: Path, workspace: Path) -> Path:
    fixture = repo / "tests/unity/projects/production-e2e"
    package = repo / "Packages/com.darumappap.unity-agent"
    reject_links(fixture)
    reject_links(package)
    project = workspace / "p"
    project.mkdir()
    for folder in ("Assets", "Packages", "ProjectSettings"):
        shutil.copytree(fixture / folder, project / folder)
    package_copy = workspace / "upm" / "com.darumappap.unity-agent"
    package_copy.parent.mkdir()
    shutil.copytree(package, package_copy)
    manifest_path = project / "Packages/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependencies = manifest.get("dependencies", {})
    if "com.darumappap.unity-agent" not in dependencies:
        raise RuntimeError("Fixture manifest lacks the UnityAgent dependency")
    # UPMのfile:参照はProjectのPackagesフォルダを基準に解決される。
    dependencies["com.darumappap.unity-agent"] = "file:../../upm/com.darumappap.unity-agent"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    template = repo / "src/unityagent/control_plane/resources/FullE2EProbe.txt"
    editor_template = package_copy / "Editor/Resources/FullE2EProbe.txt"
    if not template.is_file() or template.read_bytes() != editor_template.read_bytes():
        raise RuntimeError("Control Plane / Editor script templates disagree")
    if (project / "Assets/UnityAgentE2E").exists() or (project / "Assets/UnityAgentE2E.meta").exists():
        raise RuntimeError("Full E2E output is not empty")
    return project


def install_host(repo: Path, workspace: Path, evidence: Path) -> Path:
    virtual = workspace / "venv"
    venv.create(virtual, with_pip=True)
    python = virtual / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    installed = command([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", str(repo)],
                        timeout=600, output=evidence / "host-install.log")
    if installed.returncode:
        raise RuntimeError("Host CLI installation failed; see host-install.log")
    return virtual / ("Scripts/unity-agent.exe" if os.name == "nt" else "bin/unity-agent")


def cli_json(cli: Path, operation: str, project: Path, state: Path, evidence: Path, *extra: str) -> dict:
    args = [str(cli), "e2e", operation, "--project-path", str(project), "--state-root", str(state), *extra]
    run = command(args, timeout=600, output=evidence / (operation + ".log"))
    try:
        value = json.loads(run.stdout)
    except ValueError as exc:
        raise RuntimeError(f"Invalid CLI result for {operation}") from exc
    if run.returncode or value.get("status") not in ("planned", "approved", "completed"):
        raise RuntimeError(f"E2E {operation} blocked: {value.get('reason', value.get('status'))}")
    return value


def review_plan(plan: dict) -> None:
    diffs = plan.get("exact_diff", [])
    changes = {x.get("path") for x in diffs if x.get("operation") == "create"}
    if (changes != EXPECTED_ASSETS or len(diffs) != len(EXPECTED_ASSETS)
            or plan.get("target_preimage") != "absent" or plan.get("approval_required") is not True):
        raise RuntimeError("Plan contains unexpected mutations")
    if plan.get("status") != "planned" or not re.fullmatch(r"[a-f0-9]{64}", str(plan.get("plan_id", ""))):
        raise RuntimeError("Plan ID or status is invalid")
    print("\n計画された変更（新規作成のみ）:")
    for path in sorted(changes):
        print("  +", path)
    print("\n生成するC# Script:\n", plan.get("script_preview", ""))


def require_confirmation(kind: str, plan_id: str) -> None:
    expected = f"{kind} {plan_id[:8]}"
    if input(f"\n明示承認する場合のみ '{expected}' と入力してください: ").strip() != expected:
        raise RuntimeError(f"{kind} approval was not granted")


def wait_for_editor(project: Path, editor_process: subprocess.Popen, timeout: int) -> None:
    heartbeat_path = project / "Library/UnityAgent/full_e2e/heartbeat.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if editor_process.poll() is not None:
            raise RuntimeError(f"Unity Editor exited before heartbeat (exit={editor_process.returncode})")
        try:
            heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            updated = datetime.fromisoformat(heartbeat["updated_at"])
            age = abs((datetime.now(timezone.utc) - updated).total_seconds())
            if (age <= 10 and Path(heartbeat["project_root"]).resolve() == project.resolve()
                    and heartbeat["safe_mode"] is False and heartbeat["editor_version"] == "6000.3.12f1"):
                return
        except (OSError, ValueError, KeyError, TypeError):
            pass
        time.sleep(2)
    raise RuntimeError("Unity Editor heartbeat not ready; check Editor log and Package compilation")


def execute(args: argparse.Namespace) -> int:
    repo = ROOT
    editor = Path(args.editor).expanduser()
    if os.name != "nt":
        raise RuntimeError("Interactive Full E2E is currently supported on Windows only")
    if not args.plan_only and not editor.is_file():
        raise RuntimeError(f"Unity Editor was not found: {editor}")
    sha = git_source_revision(repo, args.expected_sha)
    base = Path(args.work_root).expanduser().resolve()
    if base == repo or base.is_relative_to(repo) or repo.is_relative_to(base):
        raise RuntimeError("Temporary workspace must not overlap the canonical repository")
    base.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="e2e-", dir=base))
    evidence = workspace / "evidence"
    evidence.mkdir()
    editor_process = None
    print(f"検証対象SHA: {sha}\n一時Workspace: {workspace}", flush=True)
    try:
        project = prepare_workspace(repo, workspace)
        cli = install_host(repo, workspace, evidence)
        state = workspace / "state"
        plan = cli_json(cli, "plan", project, state, evidence)
        review_plan(plan)
        (evidence / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if args.plan_only:
            print("PLAN_ONLY: Project assets were not mutated")
            return 0
        require_confirmation("MUTATION", plan["plan_id"])
        print("\nUnity Editorを起動してheartbeatを確認します。", flush=True)
        editor_process = subprocess.Popen([str(editor), "-projectPath", str(project), "-logFile", str(evidence / "editor.log")])
        wait_for_editor(project, editor_process, args.start_timeout)
        mutation = cli_json(cli, "approve", project, state, evidence, "--plan-id", plan["plan_id"])
        if mutation.get("status") != "approved" or not mutation.get("approval_ref"):
            raise RuntimeError("Mutation approval was not recorded")
        require_confirmation("SAVE", plan["plan_id"])
        save = cli_json(cli, "approve-save", project, state, evidence, "--plan-id", plan["plan_id"])
        if save.get("status") != "approved" or not save.get("save_approval_ref"):
            raise RuntimeError("Save approval was not recorded")
        result = cli_json(cli, "apply", project, state, evidence, "--plan-id", plan["plan_id"],
                          "--approval-ref", mutation["approval_ref"],
                          "--save-approval-ref", save["save_approval_ref"], "--timeout-seconds", str(args.apply_timeout))
        (evidence / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if (result.get("status") != "completed" or result.get("compile") != "passed"
                or result.get("playmode") != "passed" or not result.get("evidence_refs")
                or not result.get("control_plane_state_ref")):
            raise RuntimeError("E2E result lacks verified Compile / PlayMode / durable Evidence")
        stored = Path(result["artifact_path"])
        if not stored.is_file() or json.loads(stored.read_text(encoding="utf-8")) != result:
            raise RuntimeError("Durable E2E result does not match CLI output")
        if git_source_revision(repo, sha) != sha:
            raise RuntimeError("Source changed during execution")
        metadata = {"status": "E2E_EDITOR_VERIFIED", "source_sha": sha, "project": str(project),
                    "result_sha256": hashlib.sha256(stored.read_bytes()).hexdigest(),
                    "evidence_refs": result["evidence_refs"], "editor": "6000.3.12f1",
                    "g1_status": "BLOCKED_NOT_RUN", "workspace": str(workspace)}
        (evidence / "summary.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("E2E_EDITOR_VERIFIED; G1 remains BLOCKED_NOT_RUN")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, KeyboardInterrupt, EOFError) as exc:
        (evidence / "failure.txt").write_text(f"BLOCKED_NOT_RUN or FAIL: {exc}\n", encoding="utf-8")
        print(f"E2E NOT VERIFIED: {exc}", file=sys.stderr)
        return 1
    finally:
        print(f"証跡保存先: {evidence}", flush=True)
        if editor_process is not None and editor_process.poll() is None:
            print("Unity Editorは開いたままです。終了後、専用一時Workspaceを手動で削除できます。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Repository-owned Windows UnityAgent fixed Full E2E")
    parser.add_argument("--editor", default=r"C:\Program Files\Unity\Hub\Editor\6000.3.12f1\Editor\Unity.exe")
    parser.add_argument("--expected-sha", help="Full reviewed 40-character Git SHA")
    parser.add_argument("--work-root", default=str(Path(os.environ.get("TEMP", tempfile.gettempdir())) / "ua-e2e"))
    parser.add_argument("--start-timeout", type=int, default=900)
    parser.add_argument("--apply-timeout", type=int, default=300)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if args.expected_sha and not re.fullmatch(r"[a-f0-9]{40}", args.expected_sha):
        parser.error("--expected-sha must be a full 40-character SHA")
    if not 30 <= args.start_timeout <= 3600 or not 30 <= args.apply_timeout <= 900:
        parser.error("Timeout must be within the accepted bounds")
    try:
        return execute(args)
    except (OSError, RuntimeError) as exc:
        print(f"BLOCKED_NOT_RUN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
