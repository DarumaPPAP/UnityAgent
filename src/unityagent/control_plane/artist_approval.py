"""Editorで観測したArtist実行計画を保存し、明示approveだけで承認へ投影する。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.store.atomic_store import exclusive_file_lock, read_json, safe_id, sha256_json, write_immutable_json
from unityagent.runtime.reference_implementation.contracts import ContractValidationError
from unityagent.runtime.tooling.environment.project_identity import canonicalize_project_root
from unityagent.runtime.contracts.artist_plan import _text, _diff, _scope, _mutation_paths, _review, _digest, validate_artist_plan, artist_plan_binding, artist_decision_digest


def _plan_path(state, plan_id):
    return Path(state) / "artist-plans" / (safe_id(plan_id, "plan_id") + ".json")


def register_artist_plan(plane, project_root, run_id, command, editor_plan, context_id, context_fingerprint, scope, *, review=None):
    """PlanはMutationまたはReviewの実行許可計画。登録だけでは承認しない。"""
    if command not in {"artist.apply", "artist.cinematic", "artist.evaluate"}:
        raise ContractValidationError("Artist execution command is invalid")
    evaluating = command == "artist.evaluate"
    expected_commands = {"artist.capture"} if evaluating else {"artist.plan", "artist.preview", "artist.refine"} if command == "artist.apply" else {"artist.cinematic"}
    if not isinstance(editor_plan, dict) or editor_plan.get("schemaVersion") != "2.0" or editor_plan.get("product") != "UnityArtistCLI" or editor_plan.get("command") not in expected_commands or editor_plan.get("status") != "passed" or editor_plan.get("errors") != [] or editor_plan.get("approvalRequired") is not (False if evaluating else True) or editor_plan.get("savePerformed") is not False:
        raise ContractValidationError("Artist Plan was not observed as a successful unsaved Editor plan")
    receipt = editor_plan.get("contextReceipt")
    if not isinstance(receipt, dict) or receipt.get("receivedContextId") != _text(context_id, "context_id") or receipt.get("receivedContextFingerprint") != _text(context_fingerprint, "context_fingerprint"):
        raise ContractValidationError("Artist Plan Context Receipt is missing or mismatched")
    revision = _text(editor_plan.get("baseRevision"), "baseRevision")
    if editor_plan.get("revision") != revision:
        raise ContractValidationError("Artist Plan changed the observed Editor revision")
    diff = _diff(editor_plan.get("exactDiff"), allow_empty=evaluating)
    plan_id = editor_plan.get("captureId" if evaluating else "planId")
    plan = {"schema_version": "1.0", "kind": "artist_execution_plan", "project_root": canonicalize_project_root(_text(project_root, "project_root")), "run_id": _text(run_id, "run_id"), "command": command, "plan_id": _text(plan_id, "planId"), "base_revision": revision, "exact_diff": diff, "context_id": context_id, "context_fingerprint": context_fingerprint, "scope": _scope(scope, diff)}
    plan["mutation_paths"] = _mutation_paths(plan["project_root"], plan["scope"], editor_plan.get("mutationPaths", [] if evaluating else None), evaluating=evaluating)
    if evaluating:
        evidence = editor_plan.get("evidence")
        bindings = [item.partition(":")[2] for item in evidence if isinstance(item, str) and item.startswith("camera_binding:")] if isinstance(evidence, list) else []
        if editor_plan.get("verified") is not True or not isinstance(evidence, list) or "visual_capture" not in evidence or "capture_manifest" not in evidence or len(bindings) != 1 or not bindings[0].strip() or diff:
            raise ContractValidationError("Artist human Review requires a verified Capture and exact camera binding")
        plan["review"] = _review(review, plan_id)
        plan["capture_observation"] = {"capture_id": plan_id, "camera_binding": bindings[0], "capture_digest": sha256_json(editor_plan)}
    elif review is not None:
        raise ContractValidationError("Artist mutation cannot carry an Evaluate human decision")
    plan["plan_digest"] = _digest(plan, "plan_digest")
    validate_artist_plan(plan)
    path = _plan_path(plane.state_store.layout.root, plan["plan_id"])
    with exclusive_file_lock(path.with_suffix(".lock")):
        write_immutable_json(path, plan)
    return deepcopy(plan)


def approve_artist_plan(plane, plan_id, expires_at=None):
    """明示approve操作でだけ、レビュー済みPlanを同じ永続承認Storeへ登録する。"""
    state = plane.state_store.layout.root
    plan = validate_artist_plan(read_json(_plan_path(state, plan_id)))
    current = datetime.now(timezone.utc)
    expiry = expires_at or (current + timedelta(minutes=30)).isoformat()
    try:
        parsed_expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if parsed_expiry <= current:
            raise ValueError("expired")
    except (TypeError, ValueError, AttributeError) as exc:
        raise ContractValidationError("Artist approval requires a future timezone-aware expiry") from exc
    decision = {"schema_version": "1.0", "kind": "artist_plan_approval", "approval_decision_id": "artist-" + uuid.uuid4().hex, "status": "active", "human_decision": "approved", "revocation_epoch": 0, "expires_at": expiry, "plan": deepcopy(plan), "binding": artist_plan_binding(plan)}
    decision["decision_digest"] = artist_decision_digest(decision)
    decision["binding"]["approvalDigest"] = decision["decision_digest"]
    store = ApprovalDecisionStore(state)
    store.register(decision)
    store.bind_artist_plan(decision["approval_decision_id"], decision["binding"])
    return deepcopy(decision)
