"""固定Rock ArtifactのEditor Import / 限定Rollback。実行権限はUnityAgent Brokerが保有。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from unityagent.persistence.store.atomic_store import atomic_write_json
from unityagent.runtime.contracts.capability_contract import validate_capability_request
from unityagent.runtime.dispatcher.subprocess_dispatcher import DispatchRequest, dispatch
from unityagent.runtime.guardrails.staged_assets import StagedAssets
from unityagent.runtime.tooling.providers.native_unity_editor.native_unity_editor_provider import NativeUnityEditorProvider
from unityagent.runtime.tooling.providers.native_unity_editor.process_builder import build_execute_method_command

TARGET = "Assets/UnityAgentRockG1"
MODEL = TARGET + "/Rock.fbx"
OWNED_FILES = frozenset({
    TARGET + ".meta", MODEL, MODEL + ".meta",
    TARGET + "/Rock.mat", TARGET + "/Rock.mat.meta",
    TARGET + "/Rock.prefab", TARGET + "/Rock.prefab.meta",
    TARGET + "/Rock.unity", TARGET + "/Rock.unity.meta",
})


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_receipt(project, receipt_path, source_hash):
    """実Editorの生成物を確定Hash/GUIDで照合。観測外ファイルを所有権へ追加しない。"""
    receipt_path = Path(receipt_path)
    record = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (record.get("status") != "applied" or record.get("schema_version") != "1.0"
            or Path(record.get("project_root", "")).resolve() != Path(project).resolve()
            or record.get("source_sha256") != source_hash):
        raise ValueError("Editor Receipt project or source revision mismatch")
    owned = record.get("files")
    if not isinstance(owned, list) or {r.get("path") for r in owned} != OWNED_FILES or len(owned) != len(OWNED_FILES):
        raise ValueError("Editor Receipt does not cover exact owned Rock outputs")
    for item in owned:
        name = item["path"]
        expected_hash = item.get("sha256")
        guid = item.get("guid")
        if not (isinstance(expected_hash, str) and len(expected_hash) == 64
                and isinstance(guid, str) and len(guid) == 32):
            raise ValueError("Editor Receipt lacks file hash or GUID")
        path = Path(project) / name
        if path.is_symlink() or not path.is_file() or _hash(path) != expected_hash:
            raise ValueError("Editor generated asset differs from Receipt: " + name)
    root = Path(project) / TARGET
    all_present = {p.relative_to(project).as_posix() for p in root.rglob("*") if p.is_file()}
    if all_present | {TARGET + ".meta"} != OWNED_FILES:
        raise ValueError("Extra or missing file under Editor-owned Rock scope")
    if not isinstance(record.get("artifact_guid"), str) or len(record["artifact_guid"]) != 32:
        raise ValueError("Editor did not provide a model GUID")
    return record


class RockImportProvider:
    """No arbitrary -executeMethod. Native Editor compatibility probing is reused."""
    def __init__(self, project, state_root, *, snapshot, check_approvals,
                 dispatcher=dispatch, editor_factory=NativeUnityEditorProvider):
        self.project = Path(project).resolve(strict=True)
        self.state_root = Path(state_root).resolve()
        self.snapshot = snapshot
        self.check_approvals = check_approvals
        self.dispatcher = dispatcher
        self.editor_factory = editor_factory

    def _run_editor(self, method, ticket, *, run_id):
        native = self.editor_factory(self.project, self.snapshot)
        failure = native._safe_mode_failure() or native._check_editor_conflict()
        if failure:
            raise ValueError("Unity Editor preflight: " + str(failure))
        binary, failure = native._resolve_editor_executable()
        if failure:
            raise ValueError("Unity Editor executable unavailable: " + str(failure))
        log = self.state_root / "rock-import" / run_id / "Editor.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        command = build_execute_method_command(
            executable_path=binary, project_root=self.project, log_path=log, method_name=method)
        env = dict(os.environ)
        env["UNITYAGENT_ROCK_IMPORT_TICKET"] = str(ticket)
        return self.dispatcher(DispatchRequest(
            command=list(command.command), cwd=self.project, timeout_seconds=600, env=env))

    def execute(self, request, context, arguments):
        validate_capability_request(request)
        if (request["capability"] != "scene.mutate"
                or request.get("qualifiers") != {"workflow": "blender_rock_import"}
                or Path(request["project_root"]).resolve() != self.project
                or not context.policy_allowed or context.approval_complete is not True):
            return {"status":"failed","provider_ref":"native_rock_import",
                    "failure_class":"blocked_by_approval","evidence":[]}
        plan = arguments["plan"]
        action = arguments["action"]
        try:
            self.check_approvals(plan, action)
            work = self.state_root / "rock-import" / plan["plan_id"]
            work.mkdir(parents=True, exist_ok=True)
            result_path = work / (action + "-result.json")
            ticket_path = work / (action + "-ticket.json")
            receipt_path = work / "receipt.json"
            artifact_path = Path(plan["source_path"])
            source_hash = plan["source_sha256"]
            if action == "apply":
                if result_path.exists() or receipt_path.exists():
                    raise ValueError("Existing Editor result requires manual reconciliation")
                if _hash(artifact_path) != source_hash:
                    raise ValueError("Staging FBX changed before import")
                if (self.project / TARGET).exists() or (self.project / (TARGET + ".meta")).exists():
                    raise ValueError("Rock target scope already exists")
                self.check_approvals(plan, action)
                staged = StagedAssets(self.project, self.state_root, plan["plan_id"],
                                      check_approval=lambda digest, phase: self.check_approvals(plan, phase))
                transaction = staged.prepare({MODEL: artifact_path.read_bytes()},
                                              approval_ref=plan["approval_ref"],
                                              mutation_scope=plan["mutation_scope"])
                staged.apply(transaction)
                ticket = {"schema_version":"1.0", "project_root":str(self.project),
                          "action":"apply", "source_sha256":source_hash,
                          "receipt_path":str(receipt_path), "result_path":str(result_path)}
                atomic_write_json(ticket_path, ticket)
                response = self._run_editor(
                    "DarumaPPAP.UnityAgent.Editor.RockImportBridge.ApplyApproved",
                    ticket_path, run_id=plan["plan_id"])
                if response.get("status") != "passed" or not result_path.is_file():
                    raise RuntimeError("Editor import may have mutated Project; reconciliation required")
                output = json.loads(result_path.read_text(encoding="utf-8"))
                if output.get("status") != "applied":
                    raise RuntimeError("Editor did not confirm bounded import")
                receipt = _verify_receipt(self.project, receipt_path, source_hash)
                return {"status":"passed","provider_ref":"native_rock_import",
                        "failure_class":None,"evidence":["editor_observation","mutation_evidence"],
                        "receipt":receipt,"receipt_sha256":_hash(receipt_path),
                        "log_path":str(work / "Editor.log"),
                        "qa_acceptance":"not_observed"}
            if action == "rollback":
                if result_path.exists():
                    raise ValueError("Rollback already attempted; reconcile first")
                if not receipt_path.is_file():
                    raise ValueError("No prior Editor Receipt")
                _verify_receipt(self.project, receipt_path, source_hash)
                self.check_approvals(plan, action)
                ticket = {"schema_version":"1.0","project_root":str(self.project),
                          "action":"rollback", "source_sha256":source_hash,
                          "receipt_path":str(receipt_path), "receipt_sha256":_hash(receipt_path),
                          "result_path":str(result_path)}
                atomic_write_json(ticket_path,ticket)
                response = self._run_editor(
                    "DarumaPPAP.UnityAgent.Editor.RockImportBridge.RollbackApproved",
                    ticket_path, run_id=plan["plan_id"] + "-rollback")
                if response.get("status") != "passed" or not result_path.is_file():
                    raise RuntimeError("Editor rollback outcome uncertain; manual reconciliation required")
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if (result.get("status") != "rolled_back"
                        or (self.project / TARGET).exists()
                        or (self.project / (TARGET + ".meta")).exists()):
                    raise RuntimeError("Editor rollback was not completely observed")
                return {"status":"passed","provider_ref":"native_rock_import",
                        "failure_class":None,"evidence":["editor_observation","mutation_evidence"],
                        "rollback":"verified", "qa_acceptance":"not_observed"}
            raise ValueError("Unsupported Rock import action")
        except (ValueError, OSError, KeyError, RuntimeError) as exc:
            return {"status":"failed","provider_ref":"native_rock_import",
                    "failure_class":"not_observed", "evidence":[],
                    "reason":str(exc), "external_effects":"reconciliation_required"}
