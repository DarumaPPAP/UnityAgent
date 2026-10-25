"""CLIとEditor両方の成功・束縛を検査し、未観測のEvidenceを補完しない。"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from unityagent.runtime.tooling.environment.project_identity import same_project_root
from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand, READ_ONLY_COMMANDS, build_artist_pipeline_command
from unityagent.runtime.tooling.providers.unity_cli.result_mapper import classify_cli_failure, is_finite_number, parse_json_sequence, redact_sensitive, terminal_envelope


def matches_artist_project(value: Any, project_root: str | Path) -> bool:
    expected = str(project_root)
    return isinstance(value, str) and bool(value.strip()) and bool(expected.strip()) and same_project_root(value, expected)


def artist_failure(failure_class: str, reason: str, *, error_code: str | None = None) -> dict[str, Any]:
    result = {"status": "failed", "failure_class": failure_class, "reason": reason, "provider_ref": "unity_cli", "evidence": []}
    if error_code is not None:
        result["error_code"] = error_code
    return result


def _editor_failure(editor: dict[str, Any]) -> dict[str, Any]:
    errors = editor.get("errors")
    first = errors[0] if isinstance(errors, list) and errors and isinstance(errors[0], dict) else {}
    code = first.get("code") if isinstance(first.get("code"), str) else None
    failure = {"APPROVAL_REQUIRED": "blocked_by_approval", "STALE_REVISION": "precondition_failed", "SCOPE_VIOLATION": "scope_violation", "UNSUPPORTED_RENDER_PIPELINE_VERSION": "unsupported", "UNSUPPORTED_UNITY_VERSION": "unsupported", "UNKNOWN_RENDER_PIPELINE": "unsupported"}.get(code, "execution_failed")
    return artist_failure(failure, str(first.get("message") or "Editor Artist command failed"), error_code=code if isinstance(code, str) else None)


def _capture_observation(editor: dict[str, Any], command: ArtistCommand, project_root: str | Path) -> dict[str, Any]:
    request = parse_json_sequence(command.request_json, strict=True)[0] if command.request_json else {}
    camera = request.get("captureCameraName")
    capture_id = editor.get("captureId")
    evidence = editor["evidence"]
    bindings = [item.partition(":")[2] for item in evidence if item.partition(":")[0] == "camera_binding"]
    paths = [item.partition(":")[2] for item in evidence if item.partition(":")[0] == "color_path"]
    if not isinstance(camera, str) or not camera.strip() or bindings != [camera]:
        return artist_failure("not_observed", "Capture requires one exact requested camera binding")
    if not isinstance(capture_id, str) or re.fullmatch(r"[A-Za-z0-9_-]+", capture_id) is None or len(paths) != 1 or editor["verified"] is not True:
        return artist_failure("not_observed", "Capture identity, color path or verification is missing")
    path = Path(paths[0])
    try:
        root = Path(project_root).resolve(strict=True)
        expected = root / "Library" / "UnityArtist" / "Captures" / capture_id / "color.png"
        # 許可されたLibrary内でもリンクや親参照を許すと別ファイルの観測をCaptureに誤帰属させる。
        if not path.is_absolute() or ".." in path.parts or path != expected or path.resolve(strict=True) != expected:
            return artist_failure("scope_violation", "Capture file is outside its exact Project Library location")
        if any(item.is_symlink() or getattr(item, "is_junction", lambda: False)() for item in (path, *path.parents) if item != root and root in item.parents):
            return artist_failure("scope_violation", "Capture file contains a symbolic link or junction")
        if not path.is_file():
            return artist_failure("not_observed", "Capture file is not a regular file")
        content = path.read_bytes()
    except (OSError, ValueError, RuntimeError):
        return artist_failure("not_observed", "Capture file could not be observed")
    if not content:
        return artist_failure("not_observed", "Capture file is empty")
    # HashはHostが今読んだファイルの観測であり、Editorから受領した証拠やVisual acceptanceではない。
    return {"capture_id": capture_id, "camera_binding": camera, "host_file_observation": {"source": "host_file_observation", "color_path": str(path.resolve()), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}}


def normalize_artist_pipeline_result(*, exit_code: int, stdout: str, command: ArtistCommand, project_root: str | Path, unity_version: str, render_pipeline: str, expected_context_id: str | None = None, expected_context_fingerprint: str | None = None, expected_run_id: str | None = None, authorization: dict | None = None) -> dict[str, Any]:
    try:
        build_artist_pipeline_command("unity", project_root, command, authorization=authorization)
    except PermissionError as exc:
        return artist_failure("blocked_by_approval", str(exc))
    except (TypeError, ValueError) as exc:
        return artist_failure("precondition_failed", str(exc))
    mutation = command.name == "apply" or command.name == "cinematic" and command.operation == "apply"
    review = command.name == "evaluate"
    refinement = command.name == "refine"
    if (review or refinement) and expected_context_id is None:
        # Human Decisionは現Editorの応答だけでは認証・照合できない。
        return artist_failure("not_observed", "Human review and refinement require an observed Context binding")
    try:
        envelope = terminal_envelope(parse_json_sequence(stdout, strict=True))
    except ValueError as exc:
        return artist_failure("execution_failed", str(exc))
    if exit_code != 0 or envelope is None or envelope.get("success") is not True:
        failure, reason = classify_cli_failure(exit_code=exit_code, envelope=envelope)
        return artist_failure(failure, reason)
    if envelope.get("command") not in {"command", f"command artist.{command.name}"} or envelope.get("errors") != []:
        return artist_failure("execution_failed", "terminal CLI command or errors do not prove Artist success")
    data = envelope.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("target"), dict):
        return artist_failure("not_observed", "Pipeline target Project was not observed")
    observed_root = data["target"].get("projectPath")
    if not matches_artist_project(observed_root, project_root):
        return artist_failure("scope_violation", "Pipeline target does not match requested Project")
    raw = data.get("result")
    try:
        values = parse_json_sequence(raw, strict=True) if isinstance(raw, str) else [raw]
        editor = values[0] if len(values) == 1 else None
    except (ValueError, TypeError):
        return artist_failure("execution_failed", "Editor Artist result is malformed JSON")
    if not isinstance(editor, dict):
        return artist_failure("not_observed", "Editor Artist result is missing")
    if editor.get("command") != f"artist.{command.name}" or editor.get("schemaVersion") != "2.0" or editor.get("product") != "UnityArtistCLI":
        return artist_failure("execution_failed", "Editor command identity or schema does not match")
    if not isinstance(editor.get("status"), str):
        return artist_failure("execution_failed", "Editor status is not a string")
    if editor.get("status") in {"blocked", "failed"}:
        return _editor_failure(editor)
    if editor.get("status") != "passed" or editor.get("errors") != []:
        return artist_failure("execution_failed", "Editor did not report unambiguous success")
    booleans = ("verified", "approvalRequired", "savePerformed", "undoAvailable", "humanReview")
    if any(not isinstance(editor.get(key), bool) for key in booleans) or editor["savePerformed"] is not False:
        return artist_failure("execution_failed", "Editor result has invalid boolean fields or performed a save")
    support = editor.get("support")
    if not isinstance(support, dict) or support.get("supported") is not True or support.get("unityVersion") != unity_version or support.get("renderPipeline") != render_pipeline:
        return artist_failure("unsupported", "Editor support does not match observed Unity version and render pipeline")
    if not unity_version or render_pipeline not in {"builtin", "urp", "hdrp"}:
        return artist_failure("not_observed", "Unity version or render pipeline was not observed")
    if not all(isinstance(editor.get(key), str) and editor[key].strip() for key in ("revision", "baseRevision")):
        return artist_failure("not_observed", "Editor revision is missing")
    if (not mutation and editor["revision"] != editor["baseRevision"]) or (mutation and editor["revision"] == editor["baseRevision"]) or command.expected_revision is not None and editor["baseRevision"] != command.expected_revision:
        return artist_failure("precondition_failed", "Editor revision changed or does not match expected revision")
    evidence = editor.get("evidence")
    diff = editor.get("exactDiff")
    if not isinstance(evidence, list) or any(not isinstance(item, str) or not item.strip() for item in evidence) or not isinstance(diff, list) or not isinstance(editor.get("targets"), list):
        return artist_failure("execution_failed", "Editor evidence, exact diff or targets are malformed")
    for target in editor["targets"]:
        if not isinstance(target, dict) or not all(isinstance(target.get(key), str) for key in ("kind", "name", "scenePath", "hierarchyPath", "globalObjectId")):
            return artist_failure("execution_failed", "Editor target identity is malformed")
        field_of_view = target.get("fieldOfView")
        if not isinstance(target.get("enabled"), bool) or not is_finite_number(field_of_view):
            return artist_failure("execution_failed", "Editor target observation has invalid types")
    tokens = {item.split(":", 1)[0] for item in evidence}
    forbidden = {"human_visual_acceptance"}
    if not mutation:
        forbidden.add("mutation_evidence")
    if not review:
        forbidden.add("human_review_decision")
    if command.name != "capture":
        forbidden.add("visual_capture")
    if tokens.intersection(forbidden) or editor["humanReview"] is not review:
        return artist_failure("execution_failed", "read-only result claims mutation, capture or human acceptance")
    operation = command.operation or "inspect"
    planned = command.name in {"plan", "preview", "refine"} or command.name == "cinematic" and operation in {"plan", "preview"}
    required = set()
    if planned:
        required = {"cinematic_plan", "timeline_evidence", "exact_diff", "expected_revision"} if command.name == "cinematic" else {"visual_direction_plan", "exact_diff", "expected_revision"}
        valid_diff = bool(diff) and all(isinstance(item, dict) and all(isinstance(item.get(key), str) for key in ("target", "property", "before", "after")) and item["target"].strip() and item["property"].strip() for item in diff)
        if not isinstance(editor.get("planId"), str) or not editor["planId"].strip() or not valid_diff or editor["approvalRequired"] is not True:
            return artist_failure("not_observed", "Plan, exact diff or approval requirement is missing")
        if command.plan_id is not None and editor["planId"] != command.plan_id:
            return artist_failure("precondition_failed", "Editor returned a different Plan")
        if any(item["property"] == "Camera.fieldOfView" for item in diff):
            required.add("camera_binding")
    elif not mutation and (diff or editor["approvalRequired"]):
        return artist_failure("execution_failed", "inspection result contains an unexpected change plan")
    if mutation or review:
        if not isinstance(authorization, dict) or not authorization.get("reservationId") or editor.get("authoritySessionId") != authorization.get("sessionId") or editor.get("authorityReservationId") != authorization["reservationId"] or not isinstance(editor.get("authorityNonce"), str) or re.fullmatch(r"[0-9a-f]{32}", editor["authorityNonce"]) is None:
            return artist_failure("blocked_by_approval", "Editor authorization receipt does not match the durable Control Plane reservation")
    if mutation:
        if not isinstance(authorization.get("mutationPaths"), list) or not authorization["mutationPaths"] or editor.get("mutationPaths") != authorization["mutationPaths"]:
            return artist_failure("scope_violation", "Editor mutation paths differ from the approved Scope")
        if editor["verified"] is not True or editor["approvalRequired"] is not True or editor["undoAvailable"] is not True or editor.get("planId") != command.plan_id or not diff or diff != authorization.get("exactDiff"):
            return artist_failure("not_observed", "Editor did not prove the exact approved mutation")
        required = {"mutation_evidence", "undo_registration", "save_not_performed"}
        if command.name == "cinematic":
            required.add("timeline_evidence")
    if review:
        expected_review = {"captureId": command.capture_id, "decision": command.decision, "notes": command.notes or ""}
        if authorization.get("review") != expected_review or editor.get("captureId") != command.capture_id or not isinstance(editor.get("evaluationId"), str) or not editor["evaluationId"].strip() or f"review_decision:{command.decision}" not in evidence or editor["verified"] is not (command.decision == "accepted"):
            return artist_failure("not_observed", "Human decision, Capture or Evaluation binding is missing")
        required = {"artist_validation", "human_review_decision"}
    if refinement:
        if editor.get("evaluationId") != command.evaluation_id:
            return artist_failure("not_observed", "Refinement refers to a different Evaluation")
        required.update({"refinement_plan", "evaluation_reference"})
    if command.name == "inspect":
        required = {"visual_art_inspection", "pipeline_support_fact"}
    if command.name in {"inspect", "history"} and editor["verified"] is not True:
        return artist_failure("not_observed", "inspection was not verified by Editor")
    if command.name == "cinematic" and operation == "inspect":
        required = {"timeline_evidence"}
    if command.name == "cinematic" and operation == "inspect" and "cinematic_operation:inspect" not in evidence:
        return artist_failure("not_observed", "cinematic inspection operation was not observed")
    capture_fields = {}
    if command.name == "capture":
        required = {"visual_capture", "camera_binding", "capture_manifest", "color_path"}
        capture_fields = _capture_observation(editor, command, project_root)
        if capture_fields.get("status") == "failed":
            return capture_fields
    if not required.issubset(tokens):
        return artist_failure("not_observed", "required Editor evidence is missing")
    receipt_fields = {}
    if expected_context_id is not None or expected_context_fingerprint is not None:
        receipt = editor.get("contextReceipt")
        if not isinstance(expected_context_id, str) or not expected_context_id.strip() or not isinstance(expected_context_fingerprint, str) or not expected_context_fingerprint.strip():
            return artist_failure("precondition_failed", "expected Context binding is incomplete")
        if not isinstance(receipt, dict) or receipt.get("receivedContextId") != expected_context_id or receipt.get("receivedContextFingerprint") != expected_context_fingerprint:
            return artist_failure("not_observed", "Editor Context Receipt is missing or mismatched")
        if expected_run_id is not None and (receipt.get("runId") != expected_run_id or not matches_artist_project(receipt.get("projectRoot"), project_root)):
            return artist_failure("scope_violation", "Editor Context belongs to a different Run or Project")
        receipt_fields = {"received_context_id": receipt["receivedContextId"], "received_context_fingerprint": receipt["receivedContextFingerprint"]}
    observations = ["editor_observation"]
    if mutation:
        required.update({"exact_diff", "expected_revision"})
    return {"status": "passed", "failure_class": None, "reason": None, "provider_ref": "unity_cli", "command_id": editor["command"], "payload": redact_sensitive(editor), "evidence": ["domain_result", *observations, *sorted(required - {"color_path"})], **receipt_fields, **capture_fields}
