"""Fixed E2E probe plan owned by the UnityAgent Control Plane."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import uuid

from ControlPlane.unity_agent_control_plane import UnityAgentControlPlane
from Persistence.Approval.approval_store import ApprovalDecisionStore
from Persistence.Store.atomic_store import atomic_write_json, read_json, safe_id, sha256_bytes, sha256_json, write_immutable_json
from Policy.Security.capability_policy import policy_for_capability, policy_for_operation_kind
from Runtime.Tooling.Environment.discovery import discover_environment
from Runtime.Tooling.Environment.environment_snapshot import UnityCliSnapshot
from Runtime.Tooling.Environment.native_editor_discovery import EditorCandidate, EditorProcessObservation
from Runtime.Tooling.Environment.project_identity import canonical_scene_path, read_project_version, same_project_root
from Runtime.Tooling.Providers.UnityAgentEditor.full_e2e_provider import FullE2EEditorProvider
from Runtime.Tooling.capability_resolver import ResolutionContext


PROBE_DIRECTORY = "Assets/UnityAgentE2E"
SCENE_PATH = PROBE_DIRECTORY + "/FullE2EScene.unity"
MATERIAL_PATH = PROBE_DIRECTORY + "/FullE2EMaterial.mat"
SCRIPT_PATH = PROBE_DIRECTORY + "/FullE2EProbe.cs"
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_TEMPLATE = Path(__file__).resolve().parent / "Resources/FullE2EProbe.txt"
CREATED_PATHS = (
    PROBE_DIRECTORY + ".meta",
    SCENE_PATH, SCENE_PATH + ".meta",
    MATERIAL_PATH, MATERIAL_PATH + ".meta",
    SCRIPT_PATH, SCRIPT_PATH + ".meta",
)


def _plan_path(state_root: Path, plan_id: str) -> Path:
    return state_root / "full_e2e/plans" / (safe_id(plan_id, "plan_id") + ".json")


def _validate_project(project_root: Path) -> str:
    if not all((project_root / name).is_dir() for name in ("Assets", "Packages", "ProjectSettings")):
        raise ValueError("Unity project markers are missing")
    version = read_project_version(project_root)
    if not version:
        raise ValueError("ProjectVersion.txt does not provide a Unity version")
    canonical_scene_path(project_root, SCENE_PATH, require_exists=False)
    if (project_root / PROBE_DIRECTORY).exists() or (project_root / (PROBE_DIRECTORY + ".meta")).exists():
        raise ValueError("E2E output directory or its meta file already exists; no overwrite is allowed")
    return version


def plan_full_e2e(project_root: str | Path, state_root: str | Path) -> dict[str, Any]:
    """Preview an immutable create-only diff without writing into the Unity project."""
    project = Path(project_root).expanduser().resolve(strict=True)
    state = Path(state_root).expanduser().resolve(strict=False)
    if state == project or project in state.parents:
        raise ValueError("E2E state must be stored outside the Unity project")
    version = _validate_project(project)
    script_bytes = SCRIPT_TEMPLATE.read_bytes()
    script_hash = sha256_bytes(script_bytes)
    core = {
        "schema_version": "1.0",
        "project_root": str(project),
        "project_version": version,
        "target_preimage": "absent",
        "scene_path": SCENE_PATH,
        "material_path": MATERIAL_PATH,
        "material_shader_candidates": ["Universal Render Pipeline/Unlit", "Unlit/Color", "Standard"],
        "script_path": SCRIPT_PATH,
        "script_sha256": script_hash,
        "script_preview": script_bytes.decode("utf-8"),
        "object_name": "FullE2EProbeCube",
        "scene_object_diff": {"operation": "create", "name": "FullE2EProbeCube", "primitive": "Cube",
                              "component": "FullE2EProbe", "material_path": MATERIAL_PATH},
        "exact_diff": [{"path": path, "operation": "create"} for path in CREATED_PATHS],
        "undo_path": "別途明示承認を得た後、Unity EditorのProjectウィンドウでAssets/UnityAgentE2Eを削除し、.metaと差分を確認する",
    }
    plan_id = sha256_json(core).split(":", 1)[1]
    plan = {**core, "plan_id": plan_id, "status": "planned", "approval_required": True}
    stored = _plan_path(state, plan_id)
    if stored.is_file():
        if read_json(stored) != plan:
            raise ValueError("immutable E2E plan conflicts with the current template")
    else:
        write_immutable_json(stored, plan)
    return plan


def _load_plan(project_root: str | Path, state_root: str | Path, plan_id: str) -> dict[str, Any]:
    project = Path(project_root).expanduser().resolve(strict=True)
    plan = read_json(_plan_path(Path(state_root).expanduser().resolve(strict=False), plan_id))
    if plan.get("plan_id") != plan_id or plan.get("status") != "planned":
        raise ValueError("E2E plan identifier or status is invalid")
    if not same_project_root(str(project), str(plan.get("project_root") or "")):
        raise ValueError("E2E plan belongs to another Unity project")
    # 承認・実行の直前にTemplate hash、Unity version、対象Assetと未作成状態を再確認する。
    fresh = plan_full_e2e(project, state_root)
    if fresh != plan:
        raise ValueError("E2E plan no longer matches the project or template")
    return plan


def _approve_full_e2e(project_root: str | Path, state_root: str | Path, plan_id: str, kind: str) -> dict[str, Any]:
    plan = _load_plan(project_root, state_root, plan_id)
    now = datetime.now(timezone.utc)
    scope_paths = ([SCENE_PATH, SCENE_PATH + ".meta"] if kind == "save"
                   else [item["path"] for item in plan["exact_diff"]])
    decision = {
        "schema_version": "1.0",
        "approval_decision_id": "e2e-" + kind + "-" + uuid.uuid4().hex,
        "plan_id": plan_id,
        "approval_kind": kind,
        "project_root": plan["project_root"],
        "plan_digest": sha256_json(plan),
        "scope_paths": scope_paths,
        "approved_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=15)).isoformat(),
        "human_review": "approved",
        "status": "active",
        "revocation_epoch": 0,
    }
    decision["decision_digest"] = sha256_json(decision)
    ApprovalDecisionStore(state_root).register(decision)
    return {
        "status": "approved",
        "plan_id": plan_id,
        "save_approval_ref" if kind == "save" else "approval_ref": decision["approval_decision_id"],
        "expires_at": decision["expires_at"],
    }


def approve_full_e2e(project_root: str | Path, state_root: str | Path, plan_id: str) -> dict[str, Any]:
    return _approve_full_e2e(project_root, state_root, plan_id, "editor_mutation")


def approve_full_e2e_save(project_root: str | Path, state_root: str | Path, plan_id: str) -> dict[str, Any]:
    return _approve_full_e2e(project_root, state_root, plan_id, "save")


def _trusted_approval(project_root: str | Path, state_root: str | Path, plan: dict[str, Any], approval_ref: str,
                      kind: str = "editor_mutation") -> dict[str, Any]:
    record = ApprovalDecisionStore(state_root).get(safe_id(approval_ref, "approval_ref"))
    decision = record["decision"]
    digest = decision.get("decision_digest")
    if not isinstance(digest, str) or sha256_json({key: value for key, value in decision.items() if key != "decision_digest"}) != digest:
        raise ValueError("E2E approval digest does not match")
    if (
        decision.get("approval_decision_id") != approval_ref
        or decision.get("approval_kind") != kind
        or decision.get("plan_id") != plan["plan_id"]
        or decision.get("plan_digest") != sha256_json(plan)
        or not same_project_root(str(project_root), str(decision.get("project_root") or ""))
        or decision.get("scope_paths") != ([SCENE_PATH, SCENE_PATH + ".meta"] if kind == "save"
                                            else [item["path"] for item in plan["exact_diff"]])
        or decision.get("status") != "active"
        or decision.get("human_review") != "approved"
        or decision.get("revocation_epoch") != record.get("current_revocation_epoch")
        or datetime.fromisoformat(str(decision["expires_at"])) <= datetime.now(timezone.utc)
    ):
        raise ValueError("E2E approval is stale, revoked or bound to a different plan")
    return decision


def _require_e2e_policy() -> None:
    mutation = policy_for_capability("scene.mutate")
    save = policy_for_operation_kind("save")
    if (
        mutation.get("operation_kind") != "editor_mutation"
        or mutation.get("default_permission") != "explicit_mutation_permission"
        or mutation.get("approval_requirement") != "required_for_project_asset_or_settings_change"
        or mutation.get("requires_mutation_scope") is not True
        or save.get("default_permission") != "separate_save_permission"
        or save.get("approval_requirement") != "required_for_project_asset_or_settings_change"
    ):
        raise ValueError("Policy does not allow the fixed E2E mutation and separate Scene save")


def apply_full_e2e(project_root: str | Path, state_root: str | Path, plan_id: str, approval_ref: str, save_approval_ref: str,
                   *, definition_fingerprint: dict[str, str], timeout_seconds: float = 180.0) -> dict[str, Any]:
    project = Path(project_root).expanduser().resolve(strict=True)
    state = Path(state_root).expanduser().resolve(strict=False)
    if state == project or project in state.parents:
        raise ValueError("E2E state must be stored outside the Unity project")
    plan = _load_plan(project, state, plan_id)
    _require_e2e_policy()
    approval = _trusted_approval(project, state, plan, approval_ref)
    if not save_approval_ref:
        raise ValueError("separate save approval is required before E2E apply")
    save_approval = _trusted_approval(project, state, plan, save_approval_ref, "save")
    run_id = "e2e-" + uuid.uuid4().hex
    artifact = state / "full_e2e/runs" / run_id / "result.json"
    result = {
        "status": "blocked",
        "reason": "UnityAgent Editor bridge is unavailable",
        "run_id": run_id,
        "plan_id": plan_id,
        "approval_ref": approval_ref,
        "save_approval_ref": save_approval_ref,
        "scene": "not_observed",
        "gameobject": "not_observed",
        "script": "not_observed",
        "material": "not_observed",
        "compile": "unavailable",
        "playmode": "unavailable",
        "evidence_refs": [],
        "artifact_path": str(artifact),
        "remaining_validation": "同じProjectをUnity Editorで開き、UnityAgent packageを有効にしてから新しいPlanを作成する",
    }
    def check_approvals() -> None:
        _trusted_approval(project, state, plan, approval_ref)
        _trusted_approval(project, state, plan, save_approval_ref, "save")

    provider = FullE2EEditorProvider(project, state, plan, approval, save_approval,
        check_approval=check_approvals, timeout_seconds=timeout_seconds)
    observed = provider.observe()
    if observed["status"] != "available":
        result["reason"] = "UnityAgent Editor bridge is unavailable: " + str(observed["reason"])
        atomic_write_json(artifact, result)
        return result

    heartbeat = observed["heartbeat"]
    snapshot = discover_environment(
        str(project), mutation_allowed_paths=[PROBE_DIRECTORY, PROBE_DIRECTORY + ".meta"],
        editor_candidates=[EditorCandidate(str(heartbeat["editor_path"]), str(heartbeat["editor_version"]))],
        editor_candidates_observed=True,
        editor_processes=[EditorProcessObservation(
            int(heartbeat["process_id"]), str(heartbeat["editor_path"]), "",
            str(heartbeat["project_root"]), False)],
        editor_processes_observed=True,
        unity_cli_observation=UnityCliSnapshot(False, None, None, "unavailable"),
    )
    scope = {"allowed_paths": [PROBE_DIRECTORY, PROBE_DIRECTORY + ".meta"],
             "prohibited_paths": ["ProjectSettings"]}
    required = ["editor_observation", "mutation_evidence", "compile_observation", "test_execution", "exact_diff"]
    entry = {
        "schema_version": "1.0", "request_id": run_id, "entry_point": "codex_plugin",
        "project_root": str(project), "intent": {"kind": "fixed_full_e2e_probe"},
        "route_id": "asset-data-change", "node_id": "create_compile_playmode",
        "execution_profile": "live_editor", "context_id": "asset-data-change",
        "context_fingerprint": plan_id, "task_contract_runtime_projection": {"plan_id": plan_id},
        "mutation_scope": scope, "validation_requirements": required,
        "capability_requests": [{
            "schema_version": "1.0", "capability": "scene.mutate", "project_root": str(project),
            "operation_kind": "editor_mutation", "required_evidence": required,
            "mutation_scope": scope, "approval_ref": approval_ref,
            "preferred_surface": "live_editor", "qualifiers": {"workflow": "full_e2e"},
        }],
    }
    plane = UnityAgentControlPlane(state)
    outcome = plane.execute(entry, environment_snapshot=snapshot,
        context=ResolutionContext(policy_allowed=True, approval_complete=True, approval_required=True),
        executors={"unity_agent_editor": provider},
        provider_arguments={"unity_agent_editor": {"run_id": run_id}},
        definition_fingerprint=definition_fingerprint, run_id=run_id, maximum_retry_attempts=0)
    first = outcome["results"][0]
    raw = first.get("provider_result") or {}
    result["evidence_refs"] = outcome["evidence_refs"]
    result["control_plane_state_ref"] = outcome["state_ref"]
    if raw.get("raw_result_ref"):
        raw_result = read_json(Path(raw["raw_result_ref"]))
        raw_artifact = artifact.parent / "editor-result.json"
        atomic_write_json(raw_artifact, raw_result)
        result["editor_result_artifact_path"] = str(raw_artifact)
    if outcome["status"] == "completed" and raw.get("status") == "passed":
        records = [plane.evidence_store.get(ref) for ref in outcome["evidence_refs"]]
        if len(records) == 1 and records[0].get("completion") == "verified":
            result.update({"status": "completed", "reason": None, "scene": "passed", "script": "passed",
                           "material": "passed", "gameobject": "passed", "compile": "passed", "playmode": "passed",
                           "material_shader": raw["shader_name"], "remaining_validation": None})
    else:
        result["reason"] = str(raw.get("reason") or first.get("status") or "Editor execution was not verified")
        result["compile"] = str(raw.get("compile") or "not_observed")
        result["playmode"] = str(raw.get("playmode") or "not_observed")
        if raw.get("raw_result_ref"):
            paths = set(raw_result.get("changed_paths") or [])
            for label, path in (("scene", SCENE_PATH), ("script", SCRIPT_PATH), ("material", MATERIAL_PATH)):
                if path in paths and (project / path).is_file():
                    result[label] = "created"
            if result["scene"] == "created":
                result["gameobject"] = "created"
            result["remaining_validation"] = "署名済みEditor結果と作成済みAssetを確認する。再実行には別途承認のうえUnity EditorでProbe Assetを削除する"
    atomic_write_json(artifact, result)
    return result
