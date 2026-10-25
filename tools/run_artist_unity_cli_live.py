"""専用Fixtureの全9 Artist操作を既存Control Planeから実Editorへ検証する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

from unityagent.cli import _fingerprint
from unityagent.control_plane.artist_execution import approve_artist_execution, execute_artist
from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand


ROOT = Path(__file__).resolve().parents[1]


def source_hashes():
    paths = [path for base in ("src/unityagent", "subagent/artist_subagent/tools/editor") for path in (ROOT / base).rglob("*") if path.is_file() and "_resources" not in path.parts and "__pycache__" not in path.parts and path.suffix in {".py", ".cs", ".yaml", ".json", ".asmdef"}]
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-path", type=Path, required=True)
    parser.add_argument("--camera-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = args.project_path.resolve()
    # 既存Sceneを検証都合で変更しないため、このTaskが所有する専用Fixtureだけを操作する。
    if project.name != ".artist-e2e~" or not (project / "Assets/ArtistAuthorityFixture.unity").is_file():
        parser.error("this runner requires the owned .artist-e2e~ ArtistAuthorityFixture project")
    args.output.mkdir(parents=True, exist_ok=True)
    before = source_hashes()
    run_id = "artist-live-" + uuid.uuid4().hex[:12]
    plane = UnityAgentControlPlane(args.output / "state")
    results = {}
    gates = {"all_nine_commands": "BLOCKED_NOT_RUN", "single_use_replay": "BLOCKED_NOT_RUN", "old_host_absent": "PASS" if shutil.which("unity-artist") is None else "FAIL", "source_state_stable": "BLOCKED_NOT_RUN"}

    def save(name, value):
        (args.output / (name + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def execute(command, *, active_run=run_id, **kwargs):
        name = command.name if active_run == run_id else command.name + "-cinematic"
        result = execute_artist(plane, str(project), active_run, command, definition_fingerprint=_fingerprint(), **kwargs)
        save(name, result)
        results[name] = {"status": result["status"], "durable": result.get("durable", False), "evidence_refs": result.get("evidence_refs", [])}
        if result["status"] != "completed" or not result.get("durable"):
            raise RuntimeError(f"{name} did not complete with durable Evidence: {result.get('resolution')}")
        return result

    try:
        inspected = execute(ArtistCommand("inspect"))
        cameras = [item for item in inspected["provider_result"]["payload"]["targets"] if item.get("kind") == "camera" and item.get("name") == args.camera_name]
        if len(cameras) != 1:
            raise ValueError("Fixture camera must be uniquely observed")
        current = cameras[0]["fieldOfView"]
        target = current + 1 if current < 170 else current - 1
        intent = json.dumps({"targetName": args.camera_name, "setCameraFieldOfView": True, "cameraFieldOfView": target})
        planned = execute(ArtistCommand("plan", request_json=intent))
        plan_id = planned["approval_plan_id"]
        execute(ArtistCommand("preview", plan_id=plan_id))
        decision = approve_artist_execution(plane, str(project), run_id, plan_id)
        approval = decision["approval_decision_id"]
        execute(ArtistCommand("apply", plan_id=plan_id), approval_ref=approval)
        try:
            execute_artist(plane, str(project), run_id, ArtistCommand("apply", plan_id=plan_id), definition_fingerprint=_fingerprint(), approval_ref=approval)
        except ValueError as exc:
            gates["single_use_replay"] = "PASS" if "already" in str(exc) else "FAIL"
            save("replay-rejection", {"error": str(exc), "gate": gates["single_use_replay"]})
        else:
            gates["single_use_replay"] = "FAIL"
        captured = execute(ArtistCommand("capture", request_json=json.dumps({"captureCameraName": args.camera_name})))
        capture_id = captured["provider_result"]["payload"]["captureId"]
        review = ArtistCommand("evaluate", capture_id=capture_id, decision="needs_refine", notes="Synthetic E2E review; no human visual acceptance asserted")
        review_plan = execute_artist(plane, str(project), run_id, review, definition_fingerprint=_fingerprint())
        save("review-plan", review_plan)
        if review_plan["status"] != "planned" or review_plan["evidence_refs"]:
            raise ValueError("Review planning must not create human acceptance Evidence")
        review_approval = approve_artist_execution(plane, str(project), run_id, review_plan["approval_plan_id"])
        evaluated = execute(review, approval_ref=review_approval["approval_decision_id"])
        evaluation_id = evaluated["provider_result"]["payload"]["evaluationId"]
        execute(ArtistCommand("refine", evaluation_id=evaluation_id, request_json=json.dumps({"targetName": args.camera_name, "setCameraFieldOfView": True, "cameraFieldOfView": current})))
        execute(ArtistCommand("history"))
        execute(ArtistCommand("cinematic", operation="inspect"), active_run=run_id + "-cinematic", domain="cinematic")
        gates["all_nine_commands"] = "PASS" if len(results) == 9 else "FAIL"
    except Exception as exc:
        save("failure", {"type": type(exc).__name__, "message": str(exc)})
        gates["all_nine_commands"] = "FAIL"
    after = source_hashes()
    gates["source_state_stable"] = "PASS" if before == after else "FAIL"
    save("source-input-hashes", {"before": before, "after": after})
    summary = {"project_root": str(project), "run_id": run_id, "gates": gates, "commands": results, "human_visual_acceptance": "not_observed", "cinematic_mutation": "BLOCKED_NOT_RUN"}
    save("summary", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(value == "PASS" for value in gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
