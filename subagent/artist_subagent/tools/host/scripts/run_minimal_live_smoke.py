#!/usr/bin/env python3
"""Run the smallest live UnityArtistCLI contract against a connected Editor.

This is intentionally a disposable smoke test, not a replacement for the
release matrix. It proves the transport and safety loop with one default scene:

    Official Unity CLI/Pipeline -> artist.inspect -> plan -> preview
    -> approval guard -> approved apply -> capture -> evaluate -> refine

The script never uses eval and never edits Unity YAML. Scene setup is performed
through the official Pipeline commands exposed by the connected Editor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROJECT = ROOT / "ci" / "unity-projects" / "artist-e2e"


class SmokeFailure(RuntimeError):
    pass


def run_unity(arguments: list[str], timeout: int = 60) -> tuple[int, dict[str, Any]]:
    completed = subprocess.run(
        ["unity", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        raise SmokeFailure(
            f"Unity CLI returned no JSON (exit={completed.returncode}): {completed.stderr.strip()}"
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            f"Unity CLI returned invalid JSON (exit={completed.returncode}): {stdout}"
        ) from exc
    return completed.returncode, payload


def run_host(arguments: list[str], timeout: int = 60) -> tuple[int, dict[str, Any]]:
    completed = subprocess.run(
        ["dotnet", "run", "--project", str(ROOT / "cli" / "artist" / "UnityArtist.Cli.csproj"), "--no-restore", "--", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        raise SmokeFailure(
            f"Artist host returned no JSON (exit={completed.returncode}): {completed.stderr.strip()}"
        )
    try:
        return completed.returncode, json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            f"Artist host returned invalid JSON (exit={completed.returncode}): {stdout}"
        ) from exc


def raw_command(project: Path, command_name: str, **parameters: Any) -> tuple[int, dict[str, Any]]:
    arguments = ["command", "--project-path", str(project), command_name]
    for key, value in parameters.items():
        arguments.append(f"--{key.replace('_', '-')}")
        if isinstance(value, (dict, list)):
            arguments.append(json.dumps(value, separators=(",", ":")))
        else:
            arguments.append(str(value))
    arguments.extend(["--format", "json", "--non-interactive", "--no-banner", "--proxy-disable"])
    return run_unity(arguments)


def command(project: Path, command_name: str, **parameters: Any) -> dict[str, Any]:
    exit_code, payload = raw_command(project, command_name, **parameters)
    if exit_code != 0 or not payload.get("success"):
        raise SmokeFailure(f"{command_name} failed: {json.dumps(payload, ensure_ascii=False)}")
    result = (payload.get("data") or {}).get("result")
    if isinstance(result, str):
        result = json.loads(result)
    if not isinstance(result, dict):
        raise SmokeFailure(f"{command_name} did not return an object result: {payload}")
    return result


def expect_host_blocked(project: Path, command_name: str, expected_code: str, *extra: str) -> dict[str, Any]:
    exit_code, payload = run_host(
        [command_name, "--project-path", str(project), *extra, "--format", "json", "--non-interactive"]
    )
    errors = payload.get("errors") or []
    code = errors[0].get("code") if errors else None
    if exit_code == 0 or payload.get("status") != "blocked" or code != expected_code:
        raise SmokeFailure(
            f"Artist host was expected to block with {expected_code}: {json.dumps(payload, ensure_ascii=False)}"
        )
    return payload


def evidence_path(result: dict[str, Any]) -> Path:
    for item in result.get("evidence", []):
        if item.startswith("color_path:"):
            return Path(item.removeprefix("color_path:"))
    raise SmokeFailure(f"Capture result did not expose color_path evidence: {result}")


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SmokeFailure(f"Capture is not a PNG: {path}")
    if data[12:16] != b"IHDR":
        raise SmokeFailure(f"PNG has no IHDR: {path}")
    return struct.unpack(">II", data[16:24])


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-path", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument(
        "--reuse-scene",
        action="store_true",
        help="Reuse the currently open scene; useful for a prepared URP/HDRP fixture.",
    )
    args = parser.parse_args()
    project = args.project_path.resolve()

    if not args.reuse_scene:
        command(project, "create_scene", path="Assets/MinimalSmoke.unity", template="default")
    find_exit, find_payload = raw_command(project, "find_gameobjects", name="SmokeSubject")
    if find_exit != 0 or not find_payload.get("success"):
        raise SmokeFailure(f"find_gameobjects failed: {find_payload}")
    found = ((find_payload.get("data") or {}).get("result") or {}).get("objects") or []
    if not found:
        created = command(project, "create_gameobject", name="SmokeSubject", primitive="cube")
        target = created.get("hierarchyPath") or "/SmokeSubject"
        command(project, "set_transform", target=target, position=[0, 0, 4], scale=[1, 1, 1])

    inspect = command(project, "artist.inspect")
    if not inspect["verified"] or not inspect["support"]["supported"]:
        raise SmokeFailure(f"Artist support is not verified: {inspect}")
    if inspect["support"]["transport"] != "official_unity_cli_pipeline":
        raise SmokeFailure(f"Unexpected transport: {inspect}")

    expect_host_blocked(project, "apply", "PLAN_ID_REQUIRED")
    intent = {
        "workflow": "lookdev",
        "setFog": True,
        "fogDensity": 0.02,
        "requestedChannels": ["environment"],
    }
    plan = command(project, "artist.plan", request_json=intent)
    preview = command(project, "artist.preview", plan_id=plan["planId"], expected_revision=plan["revision"])
    if not preview["approvalRequired"] or not preview["exactDiff"]:
        raise SmokeFailure(f"Plan/preview did not expose an exact approval diff: {preview}")
    expect_host_blocked(
        project,
        "apply",
        "APPROVAL_REQUIRED",
        "--plan-id",
        plan["planId"],
        "--expected-revision",
        plan["revision"],
    )
    applied = command(
        project,
        "artist.apply",
        plan_id=plan["planId"],
        expected_revision=plan["revision"],
        approval_token="minimal-live-smoke-approved",
    )
    required_evidence = {"mutation_evidence", "undo_registration", "save_not_performed"}
    if not required_evidence.issubset(set(applied.get("evidence", []))):
        raise SmokeFailure(f"Apply evidence is incomplete: {applied}")

    capture = command(project, "artist.capture", request_json={"captureCameraName": "Main Camera"})
    capture_file = evidence_path(capture)
    if not capture["verified"] or not capture_file.is_file() or capture_file.stat().st_size == 0:
        raise SmokeFailure(f"Capture file is not verified: {capture}")
    width, height = png_size(capture_file)

    evaluation = command(
        project,
        "artist.evaluate",
        capture_id=capture["captureId"],
        decision="needs_refine",
        notes="Minimal smoke fixture intentionally requests a refinement pass.",
    )
    if (
        evaluation.get("status") != "passed"
        or not evaluation.get("humanReview")
        or "review_decision:needs_refine" not in evaluation.get("evidence", [])
    ):
        raise SmokeFailure(f"Evaluation failed: {evaluation}")
    refined = command(
        project,
        "artist.refine",
        evaluation_id=evaluation["evaluationId"],
        request_json={
            "workflow": "lookdev",
            "setFog": True,
            "fogDensity": 0.03,
            "requestedChannels": ["environment"],
        },
    )
    if refined.get("status") != "passed" or not refined.get("approvalRequired"):
        raise SmokeFailure(f"Refine contract failed: {refined}")

    history = command(project, "artist.history")
    if history.get("status") != "passed":
        raise SmokeFailure(f"History contract failed: {history}")

    summary = {
        "status": "passed",
        "fixture": str(project.relative_to(ROOT)).replace("\\", "/"),
        "unityVersion": inspect["support"]["unityVersion"],
        "renderPipeline": inspect["support"]["renderPipeline"],
        "transport": inspect["support"]["transport"],
        "checks": [
            "artist.inspect",
            "artist.plan",
            "artist.preview",
            "approval_guard",
            "artist.apply",
            "capture_png",
            "artist.evaluate",
            "artist.refine",
            "artist.history",
        ],
        "proof": {
            "inspect_revision": inspect["revision"],
            "support": inspect["support"],
            "plan_id": plan["planId"],
            "plan_revision": plan["revision"],
            "exact_diff": plan["exactDiff"],
            "apply_revision": applied["revision"],
            "apply_base_revision": applied["baseRevision"],
            "apply_evidence": applied["evidence"],
            "capture_id": capture["captureId"],
            "capture_evidence": capture["evidence"],
            "evaluation_id": evaluation["evaluationId"],
            "evaluation_evidence": evaluation["evidence"],
            "refine_evidence": refined["evidence"],
        },
        "capture": {
            "path": str(capture_file),
            "bytes": capture_file.stat().st_size,
            "sha256": sha256_file(capture_file),
            "resolution": f"{width}x{height}",
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, SmokeFailure, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
