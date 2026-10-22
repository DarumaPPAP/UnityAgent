"""Project Root と Mutation Scope を強制する File Provider。"""
from __future__ import annotations

import hashlib
import os
import tempfile
import yaml
from pathlib import Path
from typing import Any

from unityagent.runtime.contracts.capability_contract import validate_capability_request
from unityagent.runtime.guardrails.mutation_guard import evaluate_mutation_scope
from unityagent.runtime.sandbox.workspace_guard import (
    WorkspaceGuardError,
    confined_path,
    normalize_relative_path,
    workspace_path,
)
from unityagent.runtime.tooling.environment.project_identity import same_project_root
from unityagent.runtime.tooling.providers.file.project_observation import inspect_project_files

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

    def execute(self, request, context, arguments):
        if arguments.get('bounded_csharp_union_review') is True and request.get('capability') == 'static.review':
            return self._csharp_union_review(request, context, arguments)
        if arguments.get('bounded_csharp_patch') is True and request.get('capability') in {'source.patch', 'static.review'}:
            return self._bounded_csharp(request, context, arguments)
        if request.get("operation_kind") != "read":
            # Hostの観測executorはApply権限を持たない。
            return _failure("unsupported", "File observation executor only accepts read operations")
        if request.get("capability") == "project.inspect":
            return self.inspect_project(request, policy_allowed=context.policy_allowed)
        if request.get("capability") == "source.read":
            relative_path = arguments.get("relative_path")
            if not isinstance(relative_path, str) or not relative_path:
                # 対象Sourceを推測して別Assetを読み取らない。
                return _failure("precondition_failed", "source.read requires an explicit relative_path")
            return self.read_text(request, relative_path=relative_path, policy_allowed=context.policy_allowed)
        return _failure("unsupported", "File observation executor does not implement this capability")

    def _csharp_union_review(self, request, context, arguments):
        from unityagent.runtime.guardrails.csharp_patch import project_revision, source_target, validate_csharp_patch
        failure = self._validate_request(request, 'static.review')
        if failure:
            return failure
        if not context.policy_allowed:
            return _failure('blocked_by_policy', 'Policy denied integration static review')
        try:
            if project_revision(self.project_root) != arguments['expected_revision'] or len(arguments['items']) != 2:
                raise ValueError('Integration static review revision differs')
            for item in arguments['items']:
                source = source_target(self.project_root, item['relative_path']).read_bytes().decode('utf-8')
                if (hashlib.sha256(source.encode('utf-8')).hexdigest() != item['result_source_sha256']
                        or source.count(item['replacement_text']) != 1):
                    raise ValueError('Integration static review Source differs')
                original = source.replace(item['replacement_text'], item['expected_text'], 1)
                if (hashlib.sha256(original.encode('utf-8')).hexdigest() != item['source_sha256']
                        or validate_csharp_patch(original, item['expected_text'], item['replacement_text']) != source):
                    raise ValueError('Integration changes a declaration or an unapproved expression')
            return {'status': 'passed', 'provider_ref': 'file', 'evidence': ['static_review'],
                    'project_revision': arguments['expected_revision']}
        except (ValueError, OSError, KeyError, UnicodeError) as exc:
            return _failure('precondition_failed', str(exc))

    def _bounded_csharp(self, request, context, arguments):
        from unityagent.runtime.guardrails.csharp_patch import patch_revisions, project_revision, validate_csharp_patch
        capability = request['capability']
        failure = self._validate_request(request, capability)
        if failure:
            return failure
        if not context.policy_allowed:
            return _failure('blocked_by_policy', 'Policy denied bounded C# execution')
        try:
            relative = arguments['relative_path']
            target = confined_path(self.project_root, relative, require_file=True)
            if capability == 'source.patch':
                if context.approval_required is not True or context.approval_complete is not True or not request.get('approval_ref'):
                    return _failure('blocked_by_approval', 'Bounded C# patch requires complete explicit approval')
                revisions = patch_revisions(self.project_root, relative, arguments['expected_text'], arguments['replacement_text'])
                if any(revisions[key] != arguments.get(key) for key in revisions):
                    return _failure('precondition_failed', 'C# patch revision or source preimage changed')
                return self.patch_text(request, relative_path=relative, expected_text=arguments['expected_text'],
                    replacement_text=arguments['replacement_text'], policy_allowed=True, approval_required=True,
                    approval_complete=True, expected_sha256=arguments['source_sha256'], preserve_newlines=True)
            source = target.read_bytes().decode('utf-8')
            if (project_revision(self.project_root) != arguments['result_revision']
                    or hashlib.sha256(source.encode('utf-8')).hexdigest() != arguments['result_source_sha256']
                    or source.count(arguments['replacement_text']) != 1):
                return _failure('precondition_failed', 'Static review source or Project revision differs')
            original = source.replace(arguments['replacement_text'], arguments['expected_text'], 1)
            if validate_csharp_patch(original, arguments['expected_text'], arguments['replacement_text']) != source:
                return _failure('scope_violation', 'Static review found a declaration or structural change')
            return {'status': 'passed', 'failure_class': None, 'provider_ref': 'file',
                    'evidence': ['static_review'], 'source_sha256': arguments['result_source_sha256'],
                    'project_revision': arguments['result_revision']}
        except (KeyError, ValueError, OSError, UnicodeError) as exc:
            return _failure('precondition_failed', str(exc))

    def inspect_project(self, request: dict[str, Any], *, policy_allowed: bool) -> dict[str, Any]:
        failure = self._validate_request(request, "project.inspect")
        if failure:
            # Project/Capability境界が成立しない読取は開始しない。
            return failure
        failure = self._authorize(request, policy_allowed=policy_allowed, approval_required=False, approval_complete=False)
        if failure:
            # Policy拒否後にProjectファイルを読み取らない。
            return failure
        try:
            observation = inspect_project_files(self.project_root)
        except (WorkspaceGuardError, OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
            return _failure("precondition_failed", str(exc))
        return {"status": "passed", "provider_ref": "file", "evidence": ["project_fact"], **observation}

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
        expected_sha256: str | None = None,
        preserve_newlines: bool = False,
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
            if preserve_newlines:
                from unityagent.runtime.guardrails.csharp_patch import source_target
                target = source_target(self.project_root, relative)
            current = target.read_bytes().decode("utf-8") if preserve_newlines else target.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError) as exc:
            return _failure("precondition_failed", f"unable to read patch target: {exc}")

        if expected_sha256 is not None and hashlib.sha256(current.encode('utf-8')).hexdigest() != expected_sha256:
            return _failure('precondition_failed', 'Source preimage digest changed before patch')
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
            if preserve_newlines:
                # inodeを共有する別名へ副作用を伝播しない。
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(updated.encode('utf-8'))
                try:
                    os.chmod(temporary, target.stat().st_mode & 0o777)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
            else:
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
