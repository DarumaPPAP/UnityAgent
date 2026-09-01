"""Project Root と Mutation Scope を強制する File Provider。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from Runtime.Contracts.capability_contract import validate_capability_request
from Runtime.Guardrails.mutation_guard import evaluate_mutation_scope
from Runtime.Sandbox.workspace_guard import (
    WorkspaceGuardError,
    confined_path,
    normalize_relative_path,
    workspace_path,
)
from Runtime.Tooling.Environment.project_identity import same_project_root

SERIALIZED_UNITY_MUTATION_SUFFIXES = frozenset({".unity", ".prefab", ".asset"})


def _failure(failure_class: str, reason: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_class": failure_class,
        "reason": reason,
        "provider_ref": "file",
        "evidence": [],
    }


class FileProvider:
    """Source read/patch だけを担当し、Unity serialized artifact の raw mutation は拒否する。"""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = workspace_path(project_root)

    def _validate_request(self, request: dict[str, Any], capability: str) -> dict[str, Any] | None:
        try:
            validate_capability_request(request)
        except Exception as exc:
            # Runtime boundary では不正契約を実行へ流さない。
            return _failure("precondition_failed", f"invalid capability request: {exc}")
        if request.get("capability") != capability:
            return _failure("unsupported", f"file provider does not execute {request.get('capability')!r} here")
        if not same_project_root(str(request.get("project_root") or ""), str(self.project_root)):
            return _failure("scope_violation", "CapabilityRequest project_root does not match File Provider project")
        return None

    @staticmethod
    def _authorize(
        request: dict[str, Any],
        *,
        policy_allowed: bool,
        approval_required: bool,
        approval_complete: bool,
    ) -> dict[str, Any] | None:
        if not policy_allowed:
            return _failure("blocked_by_policy", "Policy denied File Provider execution")
        if approval_required and (not request.get("approval_ref") or not approval_complete):
            return _failure("blocked_by_approval", "Required approval is not complete")
        return None

    def read_text(
        self,
        request: dict[str, Any],
        *,
        relative_path: str,
        policy_allowed: bool,
    ) -> dict[str, Any]:
        failure = self._validate_request(request, "source.read")
        if failure:
            return failure
        failure = self._authorize(
            request,
            policy_allowed=policy_allowed,
            approval_required=False,
            approval_complete=False,
        )
        if failure:
            return failure
        try:
            target = confined_path(self.project_root, relative_path, require_file=True)
            content = target.read_text(encoding="utf-8")
        except (WorkspaceGuardError, OSError, UnicodeError) as exc:
            return _failure("precondition_failed", str(exc))
        return {
            "status": "passed",
            "failure_class": None,
            "reason": None,
            "provider_ref": "file",
            "path": normalize_relative_path(relative_path),
            "content": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "evidence": ["source_read"],
        }

    def patch_text(
        self,
        request: dict[str, Any],
        *,
        relative_path: str,
        expected_text: str,
        replacement_text: str,
        policy_allowed: bool,
        approval_required: bool = False,
        approval_complete: bool = False,
    ) -> dict[str, Any]:
        failure = self._validate_request(request, "source.patch")
        if failure:
            return failure
        failure = self._authorize(
            request,
            policy_allowed=policy_allowed,
            approval_required=approval_required,
            approval_complete=approval_complete,
        )
        if failure:
            return failure
        if not expected_text:
            return _failure("precondition_failed", "expected_text must be non-empty")

        try:
            relative = normalize_relative_path(relative_path)
            target = confined_path(self.project_root, relative, require_file=True)
        except WorkspaceGuardError as exc:
            return _failure("scope_violation", str(exc))

        if target.suffix.casefold() in SERIALIZED_UNITY_MUTATION_SUFFIXES:
            return _failure(
                "blocked_by_policy",
                "raw mutation of .unity/.prefab/serialized .asset is prohibited for File Provider",
            )

        scope = request.get("mutation_scope") or {}
        scope_result = evaluate_mutation_scope(
            work_kind="mutation",
            changed_paths=[relative],
            allowed_paths=list(scope.get("allowed_paths") or []),
            prohibited_paths=list(scope.get("prohibited_paths") or []),
        )
        if scope_result.get("status") != "passed":
            return _failure("scope_violation", str(scope_result.get("reason") or "mutation scope rejected"))

        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return _failure("precondition_failed", f"unable to read patch target: {exc}")

        occurrence_count = current.count(expected_text)
        if occurrence_count != 1:
            return _failure(
                "precondition_failed",
                f"exact preimage must occur once; observed {occurrence_count}",
            )

        updated = current.replace(expected_text, replacement_text, 1)
        before_sha = hashlib.sha256(current.encode("utf-8")).hexdigest()
        after_sha = hashlib.sha256(updated.encode("utf-8")).hexdigest()
        try:
            target.write_text(updated, encoding="utf-8", newline="")
        except OSError as exc:
            return _failure("execution_failed", f"unable to write patch target: {exc}")

        return {
            "status": "passed",
            "failure_class": None,
            "reason": None,
            "provider_ref": "file",
            "path": relative,
            "before_sha256": before_sha,
            "after_sha256": after_sha,
            "evidence": ["source_diff"],
        }
