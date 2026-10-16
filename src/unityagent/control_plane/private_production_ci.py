"""Private G1 CI bridge. Only the UnityAgent host owns approval and durable stage transitions.

A private Workflow invokes this module from a reviewed source SHA. No GitHub event payload,
workflow input, or uploaded Actions artifact is an approval or a Persistence authority.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
import uuid

from unityagent.control_plane.rock_import import _require_plan, _file_hash
from unityagent.control_plane.task_execution import project_revision
from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
from unityagent.persistence.checkpoint.checkpoint_store import CheckpointStore
from unityagent.persistence.contracts.definition_fingerprint import validate_definition_fingerprint
from unityagent.persistence.resume.resume import evaluate_resume
from unityagent.persistence.state.state_store import StateStore
from unityagent.persistence.store.atomic_store import (
    PersistenceError, atomic_write_json, exclusive_file_lock, read_json,
    relative_ref, resolve_ref, safe_id, sha256_json, write_immutable_json,
)

STAGE_GATES = {
    "artifact": ("production_runtime", "blender_mcp", "artifact_integrity"),
    "editor": ("unity_compile", "import_prefab_scene_guid", "render_capture"),
    "visual": ("visual_acceptance",),
    "rollback": ("rollback", "lease_conflict"),
}
SOURCE_SHA = re.compile(r"^[a-f0-9]{40}$")
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone-aware expiry is required")
    return parsed.astimezone(timezone.utc)


class PrivateGitHubReview:
    """Re-fetch a review and its reviewed file using a token scoped to the private repo."""

    def __init__(self, *, repository: str, token: str, approvers: set[str], get_json=None):
        if not REPO_NAME.fullmatch(repository) or not token or not approvers:
            raise ValueError("Private repository, API token and approved reviewer allowlist are required")
        self.repository = repository
        self.token = token
        self.approvers = {x.lower() for x in approvers if x}
        self.get_json = get_json or self._get_json

    def _get_json(self, suffix: str):
        req = urllib.request.Request(
            "https://api.github.com/repos/" + self.repository + suffix,
            headers={"Accept": "application/vnd.github+json",
                     "Authorization": "Bearer " + self.token,
                     "X-GitHub-Api-Version": "2022-11-28"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.load(response)

    def verify(self, pr_number: int, expected: dict) -> dict:
        if type(pr_number) is not int or pr_number < 1:
            raise ValueError("A numeric private approval PR is required")
        repo = self.get_json("")
        if repo.get("full_name") != self.repository or repo.get("private") is not True:
            raise ValueError("Approval must belong to the configured private repository")
        pr = self.get_json(f"/pulls/{pr_number}")
        head = pr.get("head") or {}
        sha = head.get("sha")
        if (pr.get("state") != "open" or pr.get("base", {}).get("ref") != repo.get("default_branch")
                or head.get("repo", {}).get("full_name") != self.repository
                or not isinstance(sha, str) or not SOURCE_SHA.fullmatch(sha)):
            raise ValueError("Approval PR must have an unmodified private-repository head")
        actor = (pr.get("user") or {}).get("login", "").lower()
        reviews = self.get_json(f"/pulls/{pr_number}/reviews?per_page=100")
        if not isinstance(reviews, list) or len(reviews) >= 100:
            raise ValueError("Approval review list unavailable or incomplete")
        latest = {}
        for review in reviews:
            login = (review.get("user") or {}).get("login", "").lower()
            if review.get("state") in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
                latest[login] = review
        eligible = []
        for login, review in latest.items():
            if login == actor or login not in self.approvers:
                continue
            permission = self.get_json(f"/collaborators/{login}/permission")
            if permission.get("permission") not in {"admin", "maintain", "write"}:
                continue
            if review.get("state") == "CHANGES_REQUESTED":
                raise ValueError("Authorized reviewer has requested changes")
            if review.get("state") == "APPROVED" and review.get("commit_id") == sha and review.get("submitted_at"):
                eligible.append((login, review))
        if not eligible:
            raise ValueError("No current authenticated, authorized review for this commit")
        run_id = safe_id(expected["run_id"], "run_id")
        stage = expected["requested_stage"]
        kind = expected["kind"]
        # The approval document is versioned within the reviewed private PR commit,
        # not provided by workflow_dispatch or by an artifact.
        path = f"approvals/{run_id}/{stage}/{kind}.json"
        from urllib.parse import quote
        content = self.get_json(f"/contents/{quote(path, safe='/')}?ref={sha}")
        if content.get("encoding") != "base64" or content.get("type") != "file":
            raise ValueError("Reviewed approval manifest missing")
        try:
            document = json.loads(base64.b64decode(content["content"], validate=False))
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("Reviewed approval manifest is invalid") from exc
        if not isinstance(document, dict) or set(document) != set(expected) | {"expires_at"}:
            raise ValueError("Approval manifest fields differ from the bound plan")
        if any(document.get(key) != value for key, value in expected.items()):
            raise ValueError("Approval manifest does not match Run, Plan, Scope or Revision")
        if _utc(document["expires_at"]) <= datetime.now(timezone.utc):
            raise ValueError("Approval has expired")
        login, review = max(eligible, key=lambda x: x[1]["submitted_at"])
        if _utc(review["submitted_at"]) > _utc(document["expires_at"]):
            raise ValueError("Review submitted after approval expiration")
        return {"repository": self.repository, "pull_number": pr_number,
                "head_sha": sha, "review_id": review["id"],
                "reviewer": login, "submitted_at": review["submitted_at"],
                "expected": expected, "expires_at": document["expires_at"]}


def _manifest_path(store_root: Path, run_id: str) -> Path:
    return StateStore(store_root).layout.run_root(run_id) / "private-ci/manifest.json"


def _progress_path(store_root: Path, run_id: str) -> Path:
    return StateStore(store_root).layout.run_root(run_id) / "private-ci/progress.json"


def _lock_path(store_root: Path, run_id: str) -> Path:
    return StateStore(store_root).layout.run_root(run_id) / "private-ci/stage.lock"


def register_run(*, store_root, plan_id: str, run_id: str, source_revision: str):
    """Trusted local preparation, NOT a workflow_dispatch callable create-or-update."""
    root = Path(store_root).resolve(strict=True)
    plan = _require_plan(root, plan_id)
    safe_id(run_id, "run_id")
    if run_id != "rock-" + plan["job_id"] or not SOURCE_SHA.fullmatch(source_revision):
        raise ValueError("Run identity or reviewed source SHA mismatch")
    project = Path(plan["project_root"]).resolve(strict=True)
    if root == project or project in root.parents or root in project.parents:
        raise ValueError("Persistence and Unity Project must be disjoint")
    validate_definition_fingerprint(plan["definition_fingerprint"])
    if project_revision(project) != plan["project_revision"] or _file_hash(plan["source_path"]) != plan["source_sha256"]:
        raise ValueError("Source Artifact or Project changed")
    manifest = {"schema_version": "1.0", "run_id": run_id, "plan_id": plan_id,
                "plan_digest": sha256_json(plan), "source_revision": source_revision,
                "definition_fingerprint": plan["definition_fingerprint"],
                "project_root": plan["project_root"], "project_revision": plan["project_revision"],
                "source_path": plan["source_path"], "artifact_sha256": plan["source_sha256"],
                "scope_paths": plan["owned_files"], "stages": list(STAGE_GATES)}
    with exclusive_file_lock(_lock_path(root, run_id)):
        if _progress_path(root, run_id).exists():
            raise ValueError("Run already registered; never reset progress")
        write_immutable_json(_manifest_path(root, run_id), manifest)
        atomic_write_json(_progress_path(root, run_id),
                          {"schema_version": "1.0", "run_id": run_id, "status": "waiting",
                           "completed": [], "active": None,
                           "expected_project_revision": manifest["project_revision"]})
    return manifest


def _load(root, run_id, checkout_revision, *, require_project_revision=True):
    safe_id(run_id, "run_id")
    manifest = read_json(_manifest_path(root, run_id))
    state = read_json(_progress_path(root, run_id))
    if manifest.get("run_id") != run_id or state.get("run_id") != run_id:
        raise ValueError("Private CI Run identity mismatch")
    if manifest["source_revision"] != checkout_revision or not SOURCE_SHA.fullmatch(checkout_revision):
        raise ValueError("Private CI checkout SHA differs from reviewed source revision")
    plan = _require_plan(root, manifest["plan_id"])
    if sha256_json(plan) != manifest["plan_digest"] or plan["definition_fingerprint"] != manifest["definition_fingerprint"]:
        raise ValueError("Plan or Definition changed")
    if _file_hash(manifest["source_path"]) != manifest["artifact_sha256"]:
        raise ValueError("Staged FBX hash changed")
    if require_project_revision and project_revision(manifest["project_root"]) != state["expected_project_revision"]:
        raise ValueError("Project revision changed; reconciliation required")
    for entry in state["completed"]:
        receipt = read_json(resolve_ref(root, entry["receipt_ref"]))
        if sha256_json(receipt) != entry["receipt_digest"]:
            raise ValueError("Immutable completed Stage receipt changed")
        decision = evaluate_resume(store_root=root, run_id=run_id,
            checkpoint_id=entry["checkpoint_id"],
            current_definition_fingerprint=manifest["definition_fingerprint"])
        if not decision["allowed"] or decision["required_actions"]:
            raise ValueError("Stage checkpoint is not directly resumable")
    return manifest, state


def _expected(manifest, state, stage, kind):
    return {"schema_version": "1.0", "run_id": manifest["run_id"],
            "requested_stage": stage, "kind": kind,
            "plan_id": manifest["plan_id"], "plan_digest": manifest["plan_digest"],
            "source_revision": manifest["source_revision"],
            "artifact_sha256": manifest["artifact_sha256"],
            "project_revision": state["expected_project_revision"],
            "scope_paths": manifest["scope_paths"]}


def _kinds(stage: str):
    return ("mutation", "save") if stage == "editor" else (
        ("rollback",) if stage == "rollback" else ("stage",))


def begin_stage(*, store_root, run_id, stage, checkout_revision, workflow_run_id,
                approval_pulls: dict, verifier: PrivateGitHubReview):
    root = Path(store_root).resolve(strict=True)
    if stage not in STAGE_GATES or not str(workflow_run_id).isdigit():
        raise ValueError("Unknown Stage or GitHub Workflow Run")
    if set(approval_pulls) != set(_kinds(stage)) or len(set(approval_pulls.values())) != len(approval_pulls):
        raise ValueError("Each required approval kind needs its own private PR")
    with exclusive_file_lock(_lock_path(root, run_id)):
        manifest, state = _load(root, run_id, checkout_revision)
        if state["status"] != "waiting" or state["active"] is not None:
            raise ValueError("Already running or uncertain Stage: RECONCILIATION_REQUIRED")
        next_stage = list(STAGE_GATES)[len(state["completed"])] if len(state["completed"]) < len(STAGE_GATES) else None
        if stage != next_stage:
            raise ValueError("Out-of-order or already completed Stage")
        attestations = {kind: verifier.verify(approval_pulls[kind], _expected(manifest, state, stage, kind))
                        for kind in _kinds(stage)}
        # Existing Rock import code revalidates immutable local approval + expiry + revocation
        # at the Runtime/Editor boundary; the GitHub attestation is rechecked there as well.
        refs = {}
        for kind in ("mutation", "save", "rollback"):
            if kind not in attestations:
                continue
            now = datetime.now(timezone.utc)
            decision = {"schema_version": "1.0",
                        "approval_decision_id": "private-ci-" + uuid.uuid4().hex,
                        "operation": "rock_import_" + kind,
                        "plan_id": manifest["plan_id"], "plan_digest": manifest["plan_digest"],
                        "project_root": manifest["project_root"], "scope_paths": manifest["scope_paths"],
                        "approved_at": now.isoformat(), "expires_at": attestations[kind]["expires_at"],
                        "human_review": "approved", "status": "active", "revocation_epoch": 0,
                        "github_attestation": attestations[kind]}
            decision["decision_digest"] = sha256_json(decision)
            ApprovalDecisionStore(root).register(decision)
            refs[kind] = decision["approval_decision_id"]
        state["status"] = "running"
        state["active"] = {"stage": stage, "workflow_run_id": str(workflow_run_id),
                           "attestations": attestations, "approval_refs": refs}
        atomic_write_json(_progress_path(root, run_id), state)
        return {"run_id": run_id, "stage": stage, "approval_refs": refs,
                "state": "running", "production_verified": False}


def _validated_gate(root: Path, directory: Path, gate: str, manifest: dict) -> str:
    candidate = directory / (gate + ".json")
    if not candidate.is_file():
        raise ValueError("BLOCKED_NOT_RUN: missing gate evidence " + gate)
    record = read_json(candidate)
    if (record.get("gate") != gate or record.get("status") != "passed"
            or record.get("source_revision") != manifest["source_revision"]
            or record.get("source_sha256") != manifest["artifact_sha256"]
            or record.get("evidence_level") != "production_runtime" or record.get("limitation")):
        raise ValueError("Stage evidence identity, level or result differs: " + gate)
    refs = record.get("raw_refs")
    if not isinstance(refs, dict) or not refs:
        raise ValueError("Stage evidence is missing raw observations")
    for filename, digest in refs.items():
        if not isinstance(filename, str) or not isinstance(digest, str):
            raise ValueError("Invalid raw evidence mapping")
        path = (directory / filename).resolve(strict=True)
        if not path.is_relative_to(directory) or path.is_symlink():
            raise ValueError("Raw evidence escapes the private evidence directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Raw evidence hash mismatch")
    return sha256_json(record)


def complete_stage(*, store_root, run_id, stage, checkout_revision, workflow_run_id,
                   evidence_directory, verifier: PrivateGitHubReview):
    root = Path(store_root).resolve(strict=True)
    directory = Path(evidence_directory).resolve(strict=True)
    if directory == root or not directory.is_relative_to(root):
        raise ValueError("Raw Evidence must be under the protected Persistence root")
    with exclusive_file_lock(_lock_path(root, run_id)):
        manifest, state = _load(root, run_id, checkout_revision, require_project_revision=False)
        active = state.get("active")
        if (state["status"] != "running" or not isinstance(active, dict)
                or active.get("stage") != stage or active.get("workflow_run_id") != str(workflow_run_id)):
            raise ValueError("Stage handoff identity mismatch: RECONCILIATION_REQUIRED")
        for kind, attestation in active["attestations"].items():
            if verifier.verify(attestation["pull_number"], _expected(manifest, state, stage, kind)) != attestation:
                raise ValueError("Review changed/revoked between dispatch and Stage completion")
        gate_digests = {gate: _validated_gate(root, directory, gate, manifest)
                        for gate in STAGE_GATES[stage]}
        now = datetime.now(timezone.utc).isoformat()
        receipt = {"schema_version": "1.0", "run_id": run_id, "stage": stage,
                   "workflow_run_id": str(workflow_run_id), "gate_digests": gate_digests,
                   "project_revision_before": state["expected_project_revision"],
                   "project_revision_after": project_revision(manifest["project_root"]),
                   "attestations": active["attestations"], "completed_at": now}
        digest = sha256_json(receipt)
        receipt_path = StateStore(root).layout.run_root(run_id) / "private-ci/receipts" / (stage + ".json")
        write_immutable_json(receipt_path, receipt)
        receipt_ref = relative_ref(root, receipt_path)
        store = StateStore(root)
        # Keep any durable Blender / Editor Evidence produced by the canonical
        # Control Plane. Stage Gate files are NOT automatically EvidenceRecords.
        execution_path = store.layout.execution_state(run_id)
        existing_execution = store.load_execution_state(run_id) if execution_path.exists() else {}
        durable_refs = list(dict.fromkeys(existing_execution.get("evidence_refs", [])))
        workflow_path = store.layout.workflow_state(run_id)
        existing_workflow = store.load_workflow_state(run_id) if workflow_path.exists() else {}
        shared_refs = list(dict.fromkeys([*existing_workflow.get("shared_state_refs", []), receipt_ref]))
        store.save_execution_state({"schema_version": "1.0", "run_id": run_id,
            "status": "waiting" if stage != "rollback" else "completed",
            "current_step_id": stage, "current_action_id": None,
            "evidence_refs": durable_refs, "updated_at": now})
        store.save_workflow_state({"schema_version": "1.0", "run_id": run_id,
            "parent_graph_id": "private-production-ci", "active_subgraph_id": None,
            "active_node_id": stage, "shared_state_refs": shared_refs,
            "gate_state_refs": existing_workflow.get("gate_state_refs", []), "updated_at": now})
        checkpoint_id = "ci-" + stage + "-" + digest.split(":")[1][:20]
        CheckpointStore(root).create(checkpoint_id=checkpoint_id, run_id=run_id,
            reason="Private CI Stage boundary (State only; no Unity asset rollback)", loop_ids=[],
            evidence_refs=durable_refs, definition_fingerprint=manifest["definition_fingerprint"])
        state["completed"].append({"stage": stage, "receipt_ref": receipt_ref,
                                   "receipt_digest": digest, "checkpoint_id": checkpoint_id})
        state["status"] = "waiting" if len(state["completed"]) < len(STAGE_GATES) else "completed"
        state["expected_project_revision"] = receipt["project_revision_after"]
        state["active"] = None
        atomic_write_json(_progress_path(root, run_id), state)
        return {"run_id": run_id, "stage": stage, "state": state["status"],
                "checkpoint_id": checkpoint_id,
                "g1_gates_observed": sum(len(STAGE_GATES[item["stage"]]) for item in state["completed"]),
                "production_verified": state["status"] == "completed"}


def verifier_from_environment():
    token = os.environ.get("UNITYAGENT_PRIVATE_GITHUB_TOKEN", "")
    repository = os.environ.get("UNITYAGENT_PRIVATE_GITHUB_REPOSITORY", "")
    approvers = {x.strip() for x in os.environ.get("UNITYAGENT_PRIVATE_APPROVERS", "").split(",") if x.strip()}
    return PrivateGitHubReview(repository=repository, token=token, approvers=approvers)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Private G1 stage approval and resume guard")
    parser.add_argument("command", choices=("register", "begin", "complete"))
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--plan-id")
    parser.add_argument("--stage", choices=STAGE_GATES)
    parser.add_argument("--workflow-run-id")
    parser.add_argument("--approvals-json")
    parser.add_argument("--evidence-directory")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.command == "register":
        result = register_run(store_root=args.state_root, plan_id=args.plan_id,
            run_id=args.run_id, source_revision=args.source_revision)
    else:
        common = dict(store_root=args.state_root, run_id=args.run_id, stage=args.stage,
            checkout_revision=args.source_revision, workflow_run_id=args.workflow_run_id,
            verifier=verifier_from_environment())
        if args.command == "begin":
            result = begin_stage(**common, approval_pulls=json.loads(args.approvals_json))
        else:
            result = complete_stage(**common, evidence_directory=args.evidence_directory)
    if args.output:
        write_immutable_json(Path(args.output), result)
    # Approval refs only in protected --output file; never print them to CI logs.
    print(json.dumps({k: v for k, v in result.items() if k not in {"approval_refs", "attestations"}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
