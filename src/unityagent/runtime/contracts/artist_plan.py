"""Artist実行計画・Review・永続承認Decisionの共通検証契約。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path

from unityagent.persistence.store.atomic_store import PersistenceError, safe_id, sha256_json
from unityagent.runtime.reference_implementation.contracts import ContractValidationError
from unityagent.runtime.tooling.environment.project_identity import canonical_scene_path, same_project_root
from unityagent.runtime.sandbox.workspace_guard import confined_path, normalize_relative_path
from unityagent.runtime.guardrails.mutation_guard import evaluate_mutation_scope


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ContractValidationError(f"Artist {name} must be a nonempty string")
    return value


def _diff(value, *, allow_empty=False):
    if not isinstance(value, list) or not value and not allow_empty:
        raise ContractValidationError("Artist exact diff must be an observed list")
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"target", "property", "before", "after"}:
            raise ContractValidationError("Artist exact diff fields are invalid")
        for key, entry in item.items():
            _text(entry, key)
        pair = (item["target"], item["property"])
        if pair in seen:
            raise ContractValidationError("Artist exact target/property pair is duplicated")
        seen.add(pair)
    return deepcopy(value)


def _scope(scope, diff):
    if not isinstance(scope, dict):
        raise ContractValidationError("Artist reviewed scope is required")
    pairs = [{"target": item["target"], "property": item["property"]} for item in diff]
    if "exact_pairs" in scope and scope["exact_pairs"] != pairs:
        raise ContractValidationError("Artist exact diff differs from reviewed scope")
    return {**deepcopy(scope), "exact_pairs": pairs}


def _mutation_paths(project_root, scope, value, *, evaluating=False):
    if not isinstance(value, list) or (not value and not evaluating) or (value and evaluating):
        raise ContractValidationError("Artist mutationPaths must contain observed mutation paths, or be empty for Review")
    if evaluating:
        # Capture ReviewはSceneやAssetを書き換える実行許可ではない。
        return []
    root = Path(project_root).expanduser().resolve(strict=False)
    def canonical_path(item, *, mutation=False):
        _text(item, "mutation path" if mutation else "scope path")
        try:
            normalized = normalize_relative_path(item)
            if normalized != item or ":" in item or "\\" in item:
                raise ValueError("noncanonical path")
            resolved = confined_path(root, item)
            if mutation and canonical_scene_path(root, item, require_exists=False) != item:
                raise ValueError("noncanonical Assets path")
            if resolved.relative_to(root).as_posix() != item:
                raise ValueError("path aliases are not canonical")
        except (OSError, ValueError, RuntimeError) as exc:
            raise ContractValidationError("Artist mutation or scope path must be canonical and confined to Project/Assets") from exc
        return item.casefold() if os.name == "nt" else item
    if not isinstance(scope, dict) or not isinstance(scope.get("allowed_paths"), list) or not scope["allowed_paths"] or not isinstance(scope.get("prohibited_paths", []), list):
        raise ContractValidationError("Artist mutation requires explicit allowed_paths and prohibited_paths Scope")
    changed = [canonical_path(item, mutation=True) for item in value]
    if len(set(changed)) != len(changed):
        raise ContractValidationError("Artist mutationPaths contains duplicate physical paths")
    allowed = [canonical_path(item) for item in scope["allowed_paths"]]
    prohibited = [canonical_path(item) for item in scope.get("prohibited_paths", [])]
    result = evaluate_mutation_scope(work_kind="implementation", changed_paths=changed, allowed_paths=allowed, prohibited_paths=prohibited)
    if result["status"] != "passed":
        raise ContractValidationError("Artist observed mutation paths escape reviewed Scope: " + result["reason"])
    return deepcopy(value)


def _review(value, capture_id):
    if not isinstance(value, dict) or set(value) != {"captureId", "decision", "notes"} or value.get("captureId") != capture_id or value.get("decision") not in {"accepted", "rejected", "needs_refine"} or not isinstance(value.get("notes"), str) or "\0" in value["notes"]:
        raise ContractValidationError("Artist human Review must bind an exact Capture, decision and notes")
    return deepcopy(value)


def _digest(value, field):
    return sha256_json({key: item for key, item in value.items() if key != field})


def validate_artist_plan(plan):
    if not isinstance(plan, dict) or plan.get("schema_version") != "1.0" or plan.get("kind") != "artist_execution_plan" or plan.get("plan_digest") != _digest(plan, "plan_digest"):
        raise ContractValidationError("Artist Plan schema or digest is invalid")
    for key in ("project_root", "run_id", "plan_id", "base_revision", "context_id", "context_fingerprint"):
        _text(plan.get(key), key)
    try:
        if safe_id(plan["plan_id"], "plan_id") != plan["plan_id"]:
            raise ValueError("noncanonical Plan identity")
    except (PersistenceError, ValueError) as exc:
        raise ContractValidationError("Artist Plan identity is invalid") from exc
    if plan.get("command") not in {"artist.apply", "artist.cinematic", "artist.evaluate"}:
        raise ContractValidationError("Artist Plan command is invalid")
    evaluating = plan["command"] == "artist.evaluate"
    diff = _diff(plan.get("exact_diff"), allow_empty=evaluating)
    _mutation_paths(plan["project_root"], plan.get("scope"), plan.get("mutation_paths"), evaluating=evaluating)
    if evaluating:
        observation = plan.get("capture_observation")
        if diff or not isinstance(observation, dict) or observation.get("capture_id") != plan["plan_id"]:
            raise ContractValidationError("Artist Review must bind an observed Capture without mutation diff")
        _text(observation.get("camera_binding"), "camera_binding")
        _text(observation.get("capture_digest"), "capture_digest")
        _review(plan.get("review"), plan["plan_id"])
    elif "review" in plan:
        raise ContractValidationError("Artist mutation Plan cannot carry a human Review operation")
    if _scope(plan.get("scope"), diff) != plan["scope"]:
        raise ContractValidationError("Artist Plan reviewed scope is incomplete")
    return plan


def artist_plan_binding(plan):
    validate_artist_plan(plan)
    binding = {"projectRoot": plan["project_root"], "runId": plan["run_id"], "command": plan["command"], "planId": plan["plan_id"], "expectedRevision": plan["base_revision"], "exactDiff": deepcopy(plan["exact_diff"]), "receivedContextId": plan["context_id"], "receivedContextFingerprint": plan["context_fingerprint"], "scope": deepcopy(plan["scope"]), "planDigest": plan["plan_digest"]}
    if plan["command"] == "artist.evaluate":
        binding["review"] = deepcopy(plan["review"])
    else:
        binding["mutationPaths"] = deepcopy(plan["mutation_paths"])
    return binding


def artist_decision_digest(decision):
    payload = deepcopy(decision)
    payload.pop("decision_digest", None)
    if isinstance(payload.get("binding"), dict):
        payload["binding"].pop("approvalDigest", None)
    return sha256_json(payload)


def validate_artist_decision(record, *, project_root, run_id, plan_id):
    decision = record.get("decision") if isinstance(record, dict) else None
    if not isinstance(decision, dict) or decision.get("schema_version") != "1.0" or decision.get("kind") != "artist_plan_approval" or decision.get("decision_digest") != artist_decision_digest(decision):
        raise ContractValidationError("Artist approval schema, kind or digest is invalid")
    plan = validate_artist_plan(decision.get("plan"))
    if not isinstance(project_root, str) or not same_project_root(plan["project_root"], project_root) or plan["run_id"] != run_id or plan["plan_id"] != plan_id:
        raise ContractValidationError("Artist approval Project, Run or Plan binding differs")
    binding = {**artist_plan_binding(plan), "approvalDigest": decision["decision_digest"]}
    if decision.get("binding") != binding or record.get("artist_plan") != binding:
        raise ContractValidationError("Artist approval reviewed Plan binding differs")
    if decision.get("status") != "active" or decision.get("human_decision") != "approved" or record.get("current_revocation_epoch") != decision.get("revocation_epoch"):
        raise ContractValidationError("Artist approval is inactive, unreviewed or revoked")
    try:
        if datetime.fromisoformat(decision["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise ValueError("expired")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ContractValidationError("Artist approval has expired or has an invalid expiry") from exc
    return deepcopy(decision)
