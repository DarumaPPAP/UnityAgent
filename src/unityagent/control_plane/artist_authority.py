"""既存Control Plane承認に束縛した短命Editor通信。承認を発行しない。"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import secrets
import threading
from types import SimpleNamespace
from typing import Any

from unityagent.persistence.store.atomic_store import PersistenceError
from unityagent.runtime.reference_implementation.contracts import ContractValidationError
from unityagent.runtime.reference_implementation.runtime import CrossContractValidator
from unityagent.runtime.tooling.environment.project_identity import same_project_root


def reviewed_artist_plan(*, task, action, command: str, plan_id: str, exact_diff: list[dict[str, str]]) -> dict[str, Any]:
    if command not in {"artist.apply", "artist.cinematic"} or not isinstance(plan_id, str) or not plan_id.strip():
        raise ContractValidationError("Artist mutation command and Plan identity are required")
    if not isinstance(exact_diff, list) or len(exact_diff) != 1:
        raise ContractValidationError("current TypedAction approval only authorizes one exact property change")
    change = exact_diff[0]
    if not isinstance(change, dict) or set(change) != {"target", "property", "before", "after"} or any(not isinstance(value, str) or not value for value in change.values()):
        raise ContractValidationError("Artist exact diff must contain explicit string observations")
    if change["target"] != action.target["guid"] or change["property"] != action.property_path:
        raise ContractValidationError("Artist exact diff exceeds the approved target or property")
    try:
        before, after = float(change["before"]), float(change["after"])
    except ValueError as exc:
        raise ContractValidationError("Artist exact diff must contain finite numeric observations") from exc
    if not math.isfinite(before) or not math.isfinite(after) or after != action.value:
        raise ContractValidationError("Artist exact diff does not match the approved action value")
    if task.run_id != action.run_id or task.contract_digest != action.contract_digest or task.project_fingerprint != action.project_fingerprint:
        raise ContractValidationError("Artist action belongs to a different Task, Run or Project")
    return {"projectRoot": task.project["root"], "runId": task.run_id, "contractDigest": task.contract_digest, "actionDigest": action.action_digest, "approvalDigest": action.approval_digest, "command": command, "planId": plan_id, "expectedRevision": action.expected_revision, "exactDiff": deepcopy(exact_diff)}


class ArtistAuthority:
    """レビュー済みPlanの単回照合。一般的な任意コード実行のsandboxではない。"""

    def __init__(self, *, task, approval, grant, action, resolver, store, binding):
        self._plan_decision = None
        self.task, self.approval, self.grant, self.action = task, approval, grant, action
        self.resolver, self.store = resolver, store
        if resolver.store is not store:
            raise ContractValidationError("Artist authority requires the canonical durable approval store")
        expected = reviewed_artist_plan(task=task, action=action, command=binding.get("command"), plan_id=binding.get("planId"), exact_diff=binding.get("exactDiff"))
        if expected != binding:
            raise ContractValidationError("Artist plan binding differs from the approved action")
        self.binding = deepcopy(expected)
        self.session_id, self.token = secrets.token_hex(16), secrets.token_hex(32)
        self.reservation_id = None
        self._secret = secrets.token_bytes(32)
        self.descriptor_path = Path(task.project["root"]).resolve() / "Library/UnityAgent/ArtistAuthority.json"
        self._server = None
        self._thread = None

    @classmethod
    def for_plan(cls, *, resolver, store, binding, decision):
        if resolver.store is not store or not isinstance(decision, dict) or not isinstance(binding, dict):
            raise ContractValidationError("Artist authority requires a trusted durable Plan approval")
        trusted = resolver.resolve_artist_plan(decision.get("approval_decision_id"), project_root=binding.get("projectRoot"), run_id=binding.get("runId"), plan_id=binding.get("planId"))
        if trusted != decision or trusted["binding"] != binding:
            raise ContractValidationError("Artist authority differs from the trusted Plan approval")
        authority = cls.__new__(cls)
        authority.task, authority.grant, authority.action = None, None, None
        authority.approval = SimpleNamespace(approval_decision_id=trusted["approval_decision_id"])
        authority.resolver, authority.store = resolver, store
        authority.binding = deepcopy(binding)
        authority._plan_decision = deepcopy(trusted)
        authority.session_id, authority.token = secrets.token_hex(16), secrets.token_hex(32)
        authority.reservation_id = None
        authority._secret = secrets.token_bytes(32)
        authority.descriptor_path = Path(binding["projectRoot"]).resolve() / "Library/UnityAgent/ArtistAuthority.json"
        authority._server, authority._thread = None, None
        return authority

    def _validate(self):
        if self._plan_decision is not None:
            trusted = self.resolver.resolve_artist_plan(self.approval.approval_decision_id, project_root=self.binding["projectRoot"], run_id=self.binding["runId"], plan_id=self.binding["planId"])
            if trusted != self._plan_decision or trusted["binding"] != self.binding:
                raise ContractValidationError("Artist reviewed approval changed before execution")
            # 一般Planは既存単値TypedActionへの偽装をせず、専用契約で検証を完了する。
            return
        CrossContractValidator(self.resolver).validate(task=self.task, approval=self.approval, grant=self.grant, action=self.action)

    def authorize(self, request: dict[str, Any]) -> dict[str, Any]:
        nonce = request.get("nonce") if isinstance(request, dict) else ""
        result = {"allowed": False, "nonce": nonce, "sessionId": self.session_id, "reason": "invalid Artist authorization request", "reservationId": ""}
        if not isinstance(request, dict) or not isinstance(nonce, str) or re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
            # 未束縛の要求には予約を作らず、正規Editorの再試行を妨げない。
            return result
        required = {"sessionId", "nonce", "projectRoot", "command", "planId", "expectedRevision", "approvalToken", "exactDiff"}
        if self._plan_decision is not None:
            required.add("context")
            if self.binding["command"] != "artist.evaluate":
                required.add("mutationPaths")
        if self.binding["command"] == "artist.evaluate":
            required.add("review")
        if set(request) != required or request["sessionId"] != self.session_id or not isinstance(request["approvalToken"], str) or re.fullmatch(r"[0-9a-f]{64}", request["approvalToken"]) is None or not hmac.compare_digest(request["approvalToken"], self.token):
            # 非空Tokenや他セッションの要求を承認Decisionと取り違えない。
            return result
        if not isinstance(request["projectRoot"], str) or not same_project_root(request["projectRoot"], self.binding["projectRoot"]):
            # Project外からの要求を永続化する前に拒否する。
            return result
        if any(request[key] != self.binding[key] for key in ("command", "planId", "expectedRevision", "exactDiff")):
            # レビュー後に差分を変更した要求を承認済みPlanとして実行しない。
            return result
        if self._plan_decision is not None:
            expected_context = {"contextId": self.binding["receivedContextId"], "contextFingerprint": self.binding["receivedContextFingerprint"], "projectRoot": self.binding["projectRoot"], "runId": self.binding["runId"]}
            if request["context"] != expected_context or self.binding["command"] != "artist.evaluate" and request["mutationPaths"] != self.binding["mutationPaths"]:
                # 直接Pipeline呼出しでも、受領したContextと実対象パスが承認内容に一致する必要がある。
                return result
        if self.binding["command"] == "artist.evaluate" and request["review"] != self.binding["review"]:
            # Human Decisionと注記は署名済みでも、明示レビューした3値との一致が必要。
            return result
        try:
            reservation_id = secrets.token_hex(16)
            with self.resolver.execution_guard():
                self.store.consume_artist_plan(self.approval.approval_decision_id, self.binding, validate=self._validate, reservation_id=reservation_id)
        except (ContractValidationError, PersistenceError, OSError) as exc:
            result["reason"] = str(exc)
            return result
        self.reservation_id = reservation_id
        result.update(allowed=True, reason="approved execution started", reservationId=reservation_id)
        return result

    def __enter__(self):
        self._validate()
        authority = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # Tokenや署名を標準HTTPアクセスログへ流さない。
                pass

            def do_POST(self):
                self.connection.settimeout(3)
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if self.path != "/authorize" or not 0 < size <= 65536 or self.headers.get("Transfer-Encoding") is not None:
                        self.send_error(400)
                        return
                    body = self.rfile.read(size)
                    signature = hmac.new(authority._secret, b"request\n" + body, hashlib.sha256).hexdigest()
                    supplied_signature = self.headers.get("X-UnityAgent-Signature", "")
                    if re.fullmatch(r"[0-9a-f]{64}", supplied_signature) is None or not hmac.compare_digest(supplied_signature, signature):
                        self.send_error(403)
                        return
                    request = json.loads(body)
                    response = authority.authorize(request)
                except (ValueError, UnicodeError, TimeoutError):
                    self.send_error(400)
                    return
                raw = json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("X-UnityAgent-Signature", hmac.new(authority._secret, b"response\n" + raw, hashlib.sha256).hexdigest())
                self.end_headers()
                self.wfile.write(raw)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.descriptor_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = {"schemaVersion": "1", "projectRoot": self.binding["projectRoot"], "endpoint": f"http://127.0.0.1:{self._server.server_port}/authorize", "sessionId": self.session_id, "secret": self._secret.hex()}
        try:
            # 排他的作成により別runのdescriptorや利用者データを上書きしない。
            with self.descriptor_path.open("x", encoding="utf-8") as stream:
                json.dump(descriptor, stream)
            self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            self._thread.start()
        except Exception:
            self._server.server_close()
            self._server = None
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=3)
        try:
            descriptor = json.loads(self.descriptor_path.read_text(encoding="utf-8"))
            if descriptor.get("sessionId") == self.session_id:
                self.descriptor_path.unlink()
        except (FileNotFoundError, ValueError):
            # 他runの所有物や破損したファイルを後処理で削除しない。
            pass
