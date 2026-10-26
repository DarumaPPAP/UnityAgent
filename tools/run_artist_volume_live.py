"""所有FixtureのVolume/FogをControl Plane経由で検証する。"""
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


def main():
    project, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    pipeline = sys.argv[3]
    if project.name != ".artist-e2e~" or pipeline not in {"urp", "hdrp"} or not (project / "Assets/ArtistVolumeFixture.asset").is_file():
        raise ValueError("Owned Volume fixture required")
    output.mkdir(parents=True, exist_ok=True)
    plane = UnityAgentControlPlane(output / "state")
    run = "volume-live-" + uuid.uuid4().hex[:12]
    sources = source_hashes()
    paths = ["Assets/ArtistAuthorityFixture.unity", "Assets/ArtistVolumeFixture.asset"]
    before = {path: hashlib.sha256((project / path).read_bytes()).hexdigest() for path in paths}
    scope = {"allowed_paths": paths, "prohibited_paths": ["Packages", "ProjectSettings"]}
    intent = {"setVolumeLookDev": True, "volumePostExposure": 1.25, "volumeContrast": 10.5} if pipeline == "urp" else {"setFog": True, "fogDensity": 0.025}
    def execute(command, **kwargs):
        result = execute_artist(plane, str(project), run, command, definition_fingerprint=_fingerprint(), scope=scope, **kwargs)
        (output / (command.name + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if result["status"] != "completed" or not result.get("durable"):
            raise ValueError(f"Volume {command.name} failed: {result}")
        return result
    try:
        planned = execute(ArtistCommand("plan", request_json=json.dumps(intent)))
        payload = planned["provider_result"]["payload"]
        if all(change["before"] == change["after"] for change in payload["exactDiff"]):
            intent = {"setVolumeLookDev": True, "volumePostExposure": 1.5, "volumeContrast": 11.5} if pipeline == "urp" else {"setFog": True, "fogDensity": 0.02}
            planned = execute(ArtistCommand("plan", request_json=json.dumps(intent)))
            payload = planned["provider_result"]["payload"]
        if payload["support"]["renderPipeline"] != pipeline:
            raise ValueError("Observed Render Pipeline differs")
        if not any("overrideState" in item["property"] for item in payload["exactDiff"]):
            raise ValueError("Volume override state is missing from reviewed Exact Diff")
        plan_id = planned["approval_plan_id"]
        approved = approve_artist_execution(plane, str(project), run, plan_id)
        applied = execute(ArtistCommand("apply", plan_id=plan_id), approval_ref=approved["approval_decision_id"])
        result = applied["provider_result"]["payload"]
        if result["exactDiff"] != payload["exactDiff"] or result["verified"] is not True:
            raise ValueError("Actual Volume mutation does not match reviewed Plan")
        after = {path: hashlib.sha256((project / path).read_bytes()).hexdigest() for path in paths}
        if sources != source_hashes() or before != after:
            raise ValueError("Source or saved assets changed during unsaved Volume mutation")
        summary = {"status": "PASS", "pipeline": pipeline, "run_id": run, "intent": intent, "exact_diff": result["exactDiff"], "mutation_paths": result["mutationPaths"], "evidence_refs": applied["evidence_refs"], "source_hashes": sources, "disk_hashes": after}
    except Exception as exc:
        summary = {"status": "FAIL", "pipeline": pipeline, "run_id": run, "error": str(exc)}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "source_hashes"}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
