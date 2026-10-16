"""生成Assetの限定適用と、他者変更を上書きしないHash条件付きRollback。"""
from __future__ import annotations
from pathlib import Path
import os
import tempfile

from unityagent.persistence.store.atomic_store import read_json, safe_id, sha256_bytes, sha256_json, write_immutable_json
from unityagent.runtime.guardrails.mutation_guard import evaluate_mutation_scope
from unityagent.runtime.sandbox.workspace_guard import confined_path, normalize_relative_path


class StagedAssets:
    """呼出元RuntimeがLeaseを保持し、承認の再検証を各Mutation直前に行う。"""
    def __init__(self, project_root, state_root, transaction_id, *, check_approval):
        self.project = Path(project_root).resolve(strict=True)
        self.directory = Path(state_root).resolve() / 'staging' / safe_id(transaction_id)
        if self.project == self.directory or self.project in self.directory.parents:
            raise ValueError('Staging must be outside the Project')
        if not callable(check_approval):
            raise ValueError('Trusted approval resolver is required')
        self.check_approval = check_approval

    def _path(self, relative):
        normalized = normalize_relative_path(relative)
        path = self.project / normalized
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('symlink in mutation path')
        return confined_path(self.project, normalized)

    @staticmethod
    def _hash(path):
        return sha256_bytes(path.read_bytes()) if path.is_file() else None

    def prepare(self, generated, *, approval_ref, mutation_scope):
        if not generated or not approval_ref or not mutation_scope.get('allowed_paths'):
            raise ValueError('Generated assets, Approval and Mutation Scope are required')
        files = {}
        for relative, content in generated.items():
            relative = normalize_relative_path(relative)
            if not relative.startswith('Assets/') or Path(relative).suffix.lower() not in {'.fbx', '.png', '.jpg', '.tga'}:
                raise ValueError('Only bounded binary import assets can be staged; use Editor for Unity assets')
            if not isinstance(content, bytes):
                raise ValueError('Generated content must be bytes')
            for name in (relative, relative + '.meta'):
                path = self._path(name)
                before = path.read_bytes() if path.is_file() else None
                after = content if name == relative else before
                files[name] = {'before_hash': sha256_bytes(before) if before is not None else None,
                               'after_hash': sha256_bytes(after) if after is not None else None}
                for folder, payload in [('before', before), ('generated', after)]:
                    if payload is not None:
                        destination = self.directory / folder / name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if destination.exists() and destination.read_bytes() != payload:
                            raise ValueError('Staging transaction content changed')
                        destination.write_bytes(payload)
        check = evaluate_mutation_scope(work_kind='implementation', changed_paths=list(files), **mutation_scope)
        if check['status'] != 'passed':
            raise ValueError('Staging Mutation Scope violation')
        plan = {'schema_version': '1.0', 'project_root': str(self.project),
                'approval_ref': approval_ref, 'mutation_scope': mutation_scope, 'files': files}
        plan['digest'] = sha256_json(plan)
        write_immutable_json(self.directory / 'manifest.json', plan)
        return plan

    def _validate(self, plan, phase):
        stored = read_json(self.directory / 'manifest.json')
        if stored != plan or sha256_json({k: v for k, v in plan.items() if k != 'digest'}) != plan['digest']:
            raise ValueError('Staging manifest changed')
        if plan['project_root'] != str(self.project):
            raise ValueError('Staging Project mismatch')
        expected = 'before_hash' if phase == 'apply' else 'after_hash'
        source = 'generated' if phase == 'apply' else 'before'
        target_hash = 'after_hash' if phase == 'apply' else 'before_hash'
        for name, record in plan['files'].items():
            if self._hash(self._path(name)) != record[expected]:
                raise ValueError('Asset/meta conflict; manual reconciliation required: ' + name)
            if self._hash(self.directory / source / name) != record[target_hash]:
                raise ValueError('Staged bytes or restore bytes are corrupt')
        self.check_approval(plan['digest'], phase)

    def _write(self, plan, phase):
        self._validate(plan, phase)
        source = 'generated' if phase == 'apply' else 'before'
        target_hash = 'after_hash' if phase == 'apply' else 'before_hash'
        expected_hash = 'before_hash' if phase == 'apply' else 'after_hash'
        for name, record in plan['files'].items():
            target = self._path(name)
            if self._hash(target) != record[expected_hash]:
                raise ValueError('Asset/meta conflict during mutation: ' + name)
            if record[expected_hash] == record[target_hash]:
                continue
            if record[target_hash] is None:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary = tempfile.mkstemp(prefix='.unityagent-', dir=target.parent)
                try:
                    with os.fdopen(descriptor, 'wb') as stream:
                        stream.write((self.directory / source / name).read_bytes())
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, target)
                finally:
                    Path(temporary).unlink(missing_ok=True)
        return {'status': 'applied' if phase == 'apply' else 'rolled_back', 'manifest_digest': plan['digest']}

    def apply(self, plan):
        return self._write(plan, 'apply')

    def rollback(self, plan):
        return self._write(plan, 'rollback')
