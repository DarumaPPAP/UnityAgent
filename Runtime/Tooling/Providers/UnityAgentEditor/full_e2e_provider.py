"""Allowlisted live Unity Editor transport for UnityAgent's fixed E2E probe."""
from __future__ import annotations

import base64
import ctypes
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
from pathlib import Path
import platform
import time
from typing import Any, Callable, Mapping

from Persistence.Store.atomic_store import PersistenceError, atomic_write_json, exclusive_file_lock, read_json, sha256_bytes
from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Guardrails.mutation_guard import evaluate_mutation_scope
from Runtime.Tooling.Environment.project_identity import read_project_version, same_project_root
from Runtime.Tooling.Environment.native_editor_discovery import discover_editor_processes


JOB_FIELDS = ("run_id", "project_root", "plan_id", "approval_ref", "save_approval_ref", "expires_at", "script_sha256", "instance_id", "state_root", "plan_digest", "mutation_decision_digest", "save_decision_digest")
RESULT_FIELDS = ("run_id", "project_root", "plan_id", "approval_ref", "save_approval_ref", "status", "compile", "playmode", "script_sha256", "object_name", "instance_id", "shader_name", "reason")


def _failure(reason: str, failure_class: str = "precondition_failed") -> dict[str, Any]:
    return {"status": "failed", "failure_class": failure_class, "reason": reason,
            "provider_ref": "unity_agent_editor", "evidence": [], "compile": "not_observed", "playmode": "not_observed"}


def _signed_text(value: Mapping[str, Any], fields: tuple[str, ...], *, paths: bool = False) -> bytes:
    material = "\n".join("" if value[key] is None else str(value[key]) for key in fields)
    if paths:
        material += "\n" + ",".join(str(path) for path in value["changed_paths"])
    return material.encode("utf-8")


def _signature(secret: bytes, value: Mapping[str, Any], fields: tuple[str, ...], *, paths: bool = False) -> str:
    return hmac.new(secret, _signed_text(value, fields, paths=paths), hashlib.sha256).hexdigest()


class FullE2EEditorProvider:
    """The broker invokes this provider; it never accepts a caller-selected tool name."""

    def __init__(self, project_root: str | Path, state_root: str | Path, plan: Mapping[str, Any], approval: Mapping[str, Any], save_approval: Mapping[str, Any],
                 *, check_approval: Callable[[], Any], timeout_seconds: float = 180.0) -> None:
        self.project = Path(project_root).expanduser().resolve(strict=True)
        self.state = Path(state_root).expanduser().resolve()
        self.plan = dict(plan)
        self.approval = dict(approval)
        self.save_approval = dict(save_approval)
        self.check_approval = check_approval
        self.timeout_seconds = timeout_seconds
        self.bridge = self.project / "Library/UnityAgent/full_e2e"

    def observe(self) -> dict[str, Any]:
        """Treat only a fresh, project-bound Editor heartbeat as live state."""
        try:
            heartbeat = read_json(self.bridge / "heartbeat.json")
            timestamp = datetime.fromisoformat(str(heartbeat["updated_at"]))
            if timestamp.tzinfo is None or abs((datetime.now(timezone.utc) - timestamp).total_seconds()) > 10:
                raise ValueError("Editor heartbeat is stale")
            if not same_project_root(str(self.project), str(heartbeat["project_root"])):
                raise ValueError("Editor heartbeat belongs to another project")
            if heartbeat["editor_version"] != read_project_version(self.project):
                raise ValueError("Editor version does not match the Unity project")
            if heartbeat.get("safe_mode") is not False or not str(heartbeat.get("instance_id") or ""):
                raise ValueError("Editor Safe Mode or binding is not verified")
            if not Path(str(heartbeat["editor_path"])).is_file() or int(heartbeat["process_id"]) <= 0:
                raise ValueError("Editor executable or process identity is unavailable")
            if not self._process_matches(heartbeat):
                raise ValueError("Unity Editor process does not match its heartbeat")
            secret = base64.b64decode((self.bridge / "bridge.key").read_text(encoding="ascii"), validate=True)
            if len(secret) < 24:
                raise ValueError("Editor bridge secret is invalid")
            return {"status": "available", "heartbeat": heartbeat, "secret": secret}
        except (OSError, AttributeError, KeyError, ValueError, TypeError, PersistenceError) as exc:
            return {"status": "unavailable", "reason": str(exc)}

    def _process_matches(self, heartbeat: Mapping[str, Any]) -> bool:
        """Bind the heartbeat to an OS-observed Unity executable with the same PID."""
        editor_path = Path(str(heartbeat["editor_path"])).resolve()
        if editor_path.name.casefold() not in {"unity", "unity.exe"}:
            return False
        pid = int(heartbeat["process_id"])
        processes = discover_editor_processes(cwd=self.project)
        observed = next((item for item in processes or [] if item.pid == pid), None)
        if observed is None:
            return False
        if observed.executable_path:
            executable = Path(observed.executable_path)
        elif platform.system() == "Linux":
            executable = Path(os.readlink(f"/proc/{pid}/exe"))
        elif platform.system() == "Darwin":
            native = ctypes.CDLL("/usr/lib/libproc.dylib")
            buffer = ctypes.create_string_buffer(4096)
            if native.proc_pidpath(pid, buffer, len(buffer)) <= 0:
                return False
            executable = Path(os.fsdecode(buffer.value))
        else:
            return False
        return executable.resolve() == editor_path

    def __call__(self, request: dict[str, Any], context: Any, arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            validate_capability_request(request)
            if request["capability"] != "scene.mutate" or request.get("qualifiers") != {"workflow": "full_e2e"}:
                return _failure("Only the fixed full_e2e scene mutation is allowed", "unsupported")
            if not same_project_root(request["project_root"], str(self.project)):
                return _failure("Project Root does not match the Editor bridge", "scope_violation")
            if not context.policy_allowed or context.approval_complete is not True:
                return _failure("Policy or Approval Gate is not complete", "blocked_by_approval")
            if request.get("approval_ref") != self.approval["approval_decision_id"]:
                return _failure("Approval reference does not bind the plan", "blocked_by_approval")
            scope = request.get("mutation_scope") or {}
            if scope.get("allowed_paths") != ["Assets/UnityAgentE2E", "Assets/UnityAgentE2E.meta"] or scope.get("prohibited_paths") != ["ProjectSettings"]:
                return _failure("E2E Mutation Scope differs from the fixed plan", "scope_violation")
            self.check_approval()
            observed = self.observe()
            if observed["status"] != "available":
                return _failure(observed["reason"], "unavailable")
            heartbeat, secret = observed["heartbeat"], observed["secret"]
            run_id = str(arguments["run_id"])
            deadline = min(
                datetime.fromisoformat(self.approval["expires_at"]),
                datetime.fromisoformat(self.save_approval["expires_at"]),
                datetime.now(timezone.utc) + timedelta(seconds=self.timeout_seconds),
            )
            job = {
                "schema_version": "1.0", "run_id": run_id, "project_root": str(self.project),
                "plan_id": self.plan["plan_id"], "approval_ref": request["approval_ref"],
                "save_approval_ref": self.save_approval["approval_decision_id"],
                "expires_at": deadline.isoformat(), "script_sha256": self.plan["script_sha256"],
                "instance_id": heartbeat["instance_id"],
                "state_root": str(self.state), "plan_digest": self.approval["plan_digest"],
                "mutation_decision_digest": self.approval["decision_digest"],
                "save_decision_digest": self.save_approval["decision_digest"],
            }
            job["signature"] = _signature(secret, job, JOB_FIELDS)
            job_path = self.bridge / "jobs" / (run_id + ".json")
            result_path = self.bridge / "results" / (run_id + ".json")
            with exclusive_file_lock(self.bridge / "dispatch.lock"):
                if job_path.exists() or result_path.exists():
                    return _failure("E2E job already exists; replay is forbidden", "precondition_failed")
                submitted_at_ns = time.time_ns()
                atomic_write_json(job_path, job)
            while datetime.now(timezone.utc) < deadline:
                if result_path.is_file():
                    if result_path.stat().st_mtime_ns < submitted_at_ns:
                        return _failure("Editor result predates the submitted job", "precondition_failed")
                    return self._validate_result(read_json(result_path), request, heartbeat, secret, result_path, run_id)
                time.sleep(0.05)
            return _failure("Unity Editor did not return a result before the approval deadline", "timeout")
        except (OSError, ValueError, KeyError, TypeError, PersistenceError) as exc:
            return _failure(f"Editor bridge rejected E2E execution: {exc}")

    def _validate_result(self, result: Mapping[str, Any], request: dict[str, Any], heartbeat: Mapping[str, Any],
                         secret: bytes, result_path: Path, run_id: str) -> dict[str, Any]:
        binding_verified = False
        try:
            if result.get("schema_version") != "1.0":
                raise ValueError("Editor result schema is invalid")
            expected_signature = _signature(secret, result, RESULT_FIELDS, paths=True)
            if not hmac.compare_digest(str(result.get("signature") or ""), expected_signature):
                raise ValueError("Editor result signature is invalid")
            if (
                result["run_id"] != run_id
                or not same_project_root(str(result["project_root"]), str(self.project))
                or result["plan_id"] != self.plan["plan_id"]
                or result["approval_ref"] != request["approval_ref"]
                or result["save_approval_ref"] != self.save_approval["approval_decision_id"]
                or result["instance_id"] != heartbeat["instance_id"]
                or result["script_sha256"] != self.plan["script_sha256"]
                or result["object_name"] != self.plan["object_name"]
            ):
                raise ValueError("Editor result does not bind to the approved plan, project and Editor")
            binding_verified = True
            self.check_approval()
            if result["status"] != "passed" or result["compile"] != "passed" or result["playmode"] != "passed":
                failure = _failure(str(result.get("reason") or "Editor failed Compile or PlayMode observation"),
                                   "observed_test_failure")
                failure.update({"compile": result["compile"], "playmode": result["playmode"],
                                "raw_result_ref": str(result_path)})
                return failure
            if result["shader_name"] not in self.plan["material_shader_candidates"]:
                raise ValueError("Editor Material shader is outside the reviewed candidates")
            changed = list(result["changed_paths"])
            if len(changed) != len(set(changed)) or set(changed) != {item["path"] for item in self.plan["exact_diff"]}:
                raise ValueError("Editor Exact Diff differs from the approved create-only plan")
            scope = request["mutation_scope"]
            if evaluate_mutation_scope(work_kind="mutation", changed_paths=changed,
                                       allowed_paths=scope["allowed_paths"],
                                       prohibited_paths=scope["prohibited_paths"])["status"] != "passed":
                raise ValueError("Editor mutation escaped the approved scope")
            for relative_path in changed:
                if not (self.project / relative_path).is_file():
                    raise ValueError(f"Editor did not create the declared asset: {relative_path}")
            scoped = {"Assets/UnityAgentE2E.meta"}
            scoped.update(path.relative_to(self.project).as_posix()
                          for path in (self.project / "Assets/UnityAgentE2E").rglob("*") if path.is_file())
            if scoped != set(changed):
                raise ValueError("Editor generated undeclared files in the E2E asset directory")
            script = self.project / self.plan["script_path"]
            if sha256_bytes(script.read_bytes()) != self.plan["script_sha256"]:
                raise ValueError("Generated script differs from the reviewed template")
            return {
                "status": "passed", "failure_class": None, "reason": None,
                "provider_ref": "unity_agent_editor", "evidence": [
                    "editor_observation", "mutation_evidence", "compile_observation", "test_execution", "exact_diff"],
                "compile": "passed", "playmode": "passed", "scene_path": self.plan["scene_path"],
                "shader_name": result["shader_name"],
                "exact_diff": self.plan["exact_diff"], "raw_result_ref": str(result_path),
                "redacted_provenance": {
                    "plan_id": self.plan["plan_id"], "session_id": result["instance_id"],
                    "approval_group": "save:" + self.save_approval["approval_decision_id"],
                    "diff_digest": self.approval["plan_digest"],
                    "before_fingerprint": self.plan["plan_id"],
                    "after_fingerprint": sha256_bytes(script.read_bytes()),
                },
            }
        except (KeyError, ValueError, TypeError, OSError) as exc:
            failure = _failure(f"Editor result cannot verify the approved E2E run: {exc}", "scope_violation")
            if binding_verified:
                failure.update({
                    "compile": "reported_" + str(result.get("compile") or "unknown") + "_unverified",
                    "playmode": "reported_" + str(result.get("playmode") or "unknown") + "_unverified",
                    "raw_result_ref": str(result_path),
                })
            return failure
