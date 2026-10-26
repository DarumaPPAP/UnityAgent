"""所有Fixtureの全Cinematic kindをControl Plane承認と永続Evidenceで検証する。"""
import hashlib
import json
from pathlib import Path
import sys
import uuid

from unityagent.cli import _fingerprint
from unityagent.control_plane.artist_execution import execute_artist, approve_artist_execution
from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand
from tools.run_artist_unity_cli_live import source_hashes


SCENE = "Assets/ArtistAuthorityFixture.unity"
TIMELINE = "Assets/ArtistTimelineFixture.playable"
KINDS = ("activation", "binding", "animation", "control", "signal", "marker", "cinemachine_shot", "shot")
TRACK_TYPES = {"activation": "ActivationTrack", "animation": "AnimationTrack", "control": "ControlTrack", "signal": "SignalTrack", "cinemachine_shot": "CinemachineTrack", "shot": "CinemachineTrack"}


def cinematic_cases(suffix):
    cases = []
    for kind in KINDS:
        request = {"directorName": "Fixture Director", "trackKind": kind, "trackName": "Approved " + ("activation" if kind == "binding" else kind) + " " + suffix}
        if kind == "binding":
            request["bindingTargetName"] = "Fixture Director"
        if kind == "marker":
            request["markerTime"] = 0.1234567
        if kind in {"cinemachine_shot", "shot"}:
            request.update(bindingTargetName="Fixture Cinematic Camera A", clipStart=0.125, clipDuration=1.234567)
        cases.append((kind, request))
        if kind in {"cinemachine_shot", "shot"}:
            cases.append((kind + "-update", {**request, "bindingTargetName": "Fixture Cinematic Camera B", "clipStart": 1.125, "clipDuration": 2.234567}))
    return cases


def verify_apply(planned, applied, kind):
    diff = planned.get("exactDiff", [])
    if len(diff) != 1 or diff[0]["before"] == diff[0]["after"]:
        raise ValueError("Expected one actual Cinematic state change")
    expected_paths = [SCENE] if kind == "binding" else [SCENE, TIMELINE]
    if planned.get("mutationPaths") != expected_paths or applied.get("mutationPaths") != expected_paths or applied.get("exactDiff") != diff:
        raise ValueError("Approved exact diff or paths changed")
    required = {"mutation_evidence", "timeline_evidence", "save_not_performed"}
    if applied.get("verified") is not True or applied.get("savePerformed") is not False or not required.issubset(applied.get("evidence", [])):
        raise ValueError("Apply did not verify the actual unsaved Timeline mutation")


def verify_observed_state(planned, observed):
    approved = planned["exactDiff"][0]
    changes = observed.get("exactDiff", [])
    if len(changes) != 1 or any(changes[0].get(key) != approved.get(key) for key in ("target", "property")) or changes[0].get("before") != approved["after"]:
        raise ValueError("Reobserved Timeline state differs from approved after state")


def main():
    project = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if project.name != ".artist-e2e~" or not all((project / path).is_file() for path in (SCENE, TIMELINE)):
        raise ValueError("Owned cinematic fixture required")
    output.mkdir(parents=True, exist_ok=True)
    plane = UnityAgentControlPlane(output / "state")
    run = "cinematic-live-" + uuid.uuid4().hex[:12]
    before = source_hashes()
    files = [project / SCENE, project / TIMELINE]

    def disk_hashes():
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}

    disk_before = disk_hashes()
    scope = {"allowed_paths": [SCENE, TIMELINE], "prohibited_paths": ["Packages", "ProjectSettings"]}
    results = {}
    cases = cinematic_cases(uuid.uuid4().hex[:8])

    def save(name, value):
        (output / (name + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def execute(case, active_run, operation, *, observation=False, **kwargs):
        result = execute_artist(plane, str(project), active_run, ArtistCommand("cinematic", operation=operation, **kwargs.pop("command", {})), definition_fingerprint=_fingerprint(), scope=scope, **kwargs)
        save(case + "-" + operation + ("-observe" if observation else ""), result)
        if result["status"] != "completed" or not result.get("durable") or result.get("receipt_integrity") != "verified" or result.get("provider_result", {}).get("status") != "passed":
            raise ValueError(f"Cinematic {case}/{operation} failed: {result}")
        refs = result.get("evidence_refs", [])
        if not refs:
            raise ValueError("Cinematic step lacks durable Evidence")
        for reference in refs:
            plane.evidence_store.verify_record(reference, expected_run_id=active_run)
        results[case]["steps"].append({"operation": operation, "observation": observation, "evidence_refs": refs})
        if disk_before != disk_hashes():
            raise ValueError("Saved Scene/Timeline changed during unsaved mutation")
        return result

    error = None
    try:
        for case, request in cases:
            active_run = run + "-" + case
            kind = request["trackKind"]
            results[case] = {"status": "RUNNING", "run_id": active_run, "request": request, "steps": []}
            # 各kindの型付き要求を最初のContextへ固定し、直Provider呼出しを使わない。
            planned = execute(case, active_run, "plan", command={"request_json": json.dumps(request)})
            plan_id = planned["approval_plan_id"]
            plan_payload = planned["provider_result"]["payload"]
            preview = execute(case, active_run, "preview", command={"plan_id": plan_id})
            if preview["provider_result"]["payload"]["exactDiff"] != plan_payload["exactDiff"]:
                raise ValueError("Preview differs from Plan")
            decision = approve_artist_execution(plane, str(project), active_run, plan_id)
            save(case + "-approval", decision)
            applied = execute(case, active_run, "apply", command={"plan_id": plan_id}, approval_ref=decision["approval_decision_id"])
            verify_apply(plan_payload, applied["provider_result"]["payload"], kind)
            inspected = execute(case, active_run, "inspect", command={"request_json": json.dumps({"directorName": request["directorName"]})})
            evidence = inspected["provider_result"]["payload"].get("evidence", [])
            if kind in TRACK_TYPES and "timeline_track:" + TRACK_TYPES[kind] + ":" + request["trackName"] not in evidence:
                raise ValueError("Inspect did not observe the created exact track")
            if kind == "binding" and "binding:" + request["trackName"] + "->" + request["bindingTargetName"] not in evidence:
                raise ValueError("Inspect did not observe the actual Director binding")
            if kind in {"binding", "marker", "cinemachine_shot", "shot"}:
                # 未承認の再Planは変更せず、実状態beforeを独立に再観測する。
                observed = execute(case, active_run, "plan", observation=True, command={"request_json": json.dumps(request)})
                verify_observed_state(plan_payload, observed["provider_result"]["payload"])
            try:
                replay = execute_artist(plane, str(project), active_run, ArtistCommand("cinematic", operation="apply", plan_id=plan_id), definition_fingerprint=_fingerprint(), scope=scope, approval_ref=decision["approval_decision_id"])
            except ValueError as exc:
                if "already" not in str(exc):
                    raise
                save(case + "-replay", {"rejected": True, "error": str(exc)})
            else:
                save(case + "-replay", replay)
                raise ValueError("Reused cinematic approval was accepted")
            results[case].update(status="PASS", actual_state_verified=True, replay_rejected=True, approval_decision_id=decision["approval_decision_id"], plan_id=plan_id)
            print(json.dumps({"case": case, "status": "PASS", "run_id": active_run}), flush=True)
    except Exception as exc:
        error = str(exc)
        if results:
            results[next(reversed(results))]["status"] = "FAIL"
    after = source_hashes()
    disk_after = disk_hashes()
    stable = before == after and disk_before == disk_after
    complete = len(results) == len(cases) and all(item["status"] == "PASS" for item in results.values())
    save("input-hashes", {"source_before": before, "source_after": after, "disk_before": disk_before, "disk_after": disk_after})
    summary = {"status": "PASS" if complete and stable and error is None else "FAIL", "run_id": run, "project_root": str(project), "kinds": list(KINDS), "expected_cases": len(cases), "cases": results, "save_performed": False, "source_and_disk_stable": stable, "disk_hashes": disk_after, "error": error}
    save("summary", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
