"""別Workspace・Git管理領域・出力・Editorの物理的な分離を観測する。"""
from pathlib import Path
import hashlib
import json
import os

from unityagent.runtime.tooling.environment.environment_snapshot import validate_environment_snapshot
from unityagent.runtime.tooling.environment.project_identity import same_project_root


def _canonical(value, *, existing):
    path = Path(value).expanduser()
    if not path.is_absolute() or path != path.resolve(strict=existing):
        raise ValueError('Parallel workspace and output paths must be absolute and unaliased')
    for parent in (path, *path.parents):
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise ValueError('Parallel paths cannot contain a symlink or junction')
    return path


def _identity(path):
    info = path.stat()
    if not info.st_ino:
        raise ValueError('Physical filesystem identity is unavailable')
    return [info.st_dev, info.st_ino]


def observe_project_identities(projects):
    return {str(project): _identity(_canonical(project, existing=True)) for project in projects}


def _overlap(left, right):
    # case aliasも保守的に同一とする。異なる大文字小文字の同名Projectも並列化しない。
    a, b = str(left).replace('\\', '/').casefold().rstrip('/'), str(right).replace('\\', '/').casefold().rstrip('/')
    return a == b or a.startswith(b + '/') or b.startswith(a + '/')


def _git_directory(project):
    def pointer(base, text):
        if not text or '\n' in text or '\r' in text:
            raise ValueError('Git directory pointer is malformed')
        path = base / text
        # resolveより前に検査し、相対commondirの正規化で別名を隠さない。
        for ancestor in (path, *path.parents):
            if ancestor.is_symlink() or (hasattr(ancestor, 'is_junction') and ancestor.is_junction()):
                raise ValueError('Git directory pointer contains an alias')
        return _canonical(Path(os.path.abspath(path)), existing=True)

    for root in (project, *project.parents):
        marker = root / '.git'
        if marker.is_symlink():
            raise ValueError('Git directory alias is not a verified workspace')
        if not marker.exists():
            continue
        if marker.is_dir():
            directory = marker
        else:
            line = marker.read_text(encoding='utf-8').strip()
            if not line.startswith('gitdir: ') or '\n' in line:
                raise ValueError('Worktree Git directory cannot be verified')
            directory = pointer(root, line.removeprefix('gitdir: '))
        common = directory / 'commondir'
        if common.is_symlink() or (hasattr(common, 'is_junction') and common.is_junction()):
            raise ValueError('Git common directory pointer contains an alias')
        if common.is_file():
            directory = pointer(directory, common.read_text(encoding='utf-8').strip())
        if not (directory / 'HEAD').is_file() or not (directory / 'objects').is_dir():
            raise ValueError('Git management directory is incomplete or unobservable')
        return _identity(_canonical(directory, existing=True))
    return None


def _project(project, members):
    project = _canonical(project, existing=True)
    if not project.is_dir() or any(not (project / child).is_dir() for child in ('Assets', 'Packages', 'ProjectSettings')):
        raise ValueError('Parallel workspace must be a complete Unity Project')
    # キャッシュ・出力も含むリンクは、Editor subprocessから外へ書けるため拒否する。
    for path in project.rglob('*'):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Parallel Project contains an aliased directory or file')
        if path.is_file() and path.stat().st_nlink != 1:
            raise ValueError('Parallel Project contains a hardlinked file')
        members.add(tuple(_identity(path)))
    members.add(tuple(_identity(project)))
    return project


def verify_worker_workspaces(original_project, workers):
    """実行権限は増やさない。不明なEditor／共有Gitは直列判断、原Project別名は拒否。"""
    members = set()
    original = _project(original_project, members)
    if not isinstance(workers, list):
        raise ValueError('Worker workspace observations are required')
    projects, outputs, physical, git_ids, descriptors, reasons = [original], [], [_identity(original)], [], {}, []
    original_git = _git_directory(original)
    for worker in workers:
        name = worker['task_id']
        if not isinstance(name, str) or not name or name in descriptors:
            raise ValueError('Worker Task identity must be unique')
        worker_members = set()
        project = _project(worker['workspace'], worker_members)
        if worker_members & members:
            raise ValueError('Worker Project shares physical files or directories with another Project')
        identity = _identity(project)
        if any(_overlap(project, other) for other in projects) or identity in physical:
            raise ValueError('Workers must use distinct physical Projects outside the original')
        snapshot = worker['environment_snapshot']
        validate_environment_snapshot(snapshot)
        if (snapshot['project']['identity_status'] != 'bound'
                or not same_project_root(snapshot['project']['root'], project)):
            raise ValueError('Worker Environment Project binding differs')
        editor = snapshot['unity_editor']
        if editor['running'] is not False or editor['binding_status'] != 'not_running':
            reasons.append('editor_state_not_independent')
        output = _canonical(worker['output_root'], existing=False) if worker.get('output_root') is not None else None
        if output is not None and any(_overlap(output, other) for other in [*projects, project, *outputs]):
            raise ValueError('Worker output overlaps a Project or another output')
        if output is not None:
            ancestor = output
            while not ancestor.exists():
                ancestor = ancestor.parent
            if tuple(_identity(ancestor)) in members | worker_members:
                raise ValueError('Worker output physically aliases a Project directory')
            if ancestor == output and any(other.exists() and _identity(other) == _identity(output) for other in outputs):
                raise ValueError('Worker outputs share a physical directory')
        if any(_overlap(project, other) for other in outputs):
            raise ValueError('Worker Project overlaps a prior output')
        git_identity = _git_directory(project)
        if git_identity is not None and (git_identity == original_git or git_identity in git_ids):
            reasons.append('shared_git_directory')
        projects.append(project)
        physical.append(identity)
        if output is not None:
            outputs.append(output)
        git_ids.append(git_identity)
        members.update(worker_members)
        descriptors[name] = {'workspace': str(project), 'physical_identity': identity,
            'physical_fingerprint': 'sha256:' + hashlib.sha256(json.dumps(sorted(worker_members)).encode()).hexdigest(),
            'git_common_identity': git_identity, 'output_root': str(output) if output is not None else None}
    return {'schema_version': '1.0', 'status': 'serial' if reasons else 'verified',
            'original_project': str(original), 'original_identity': physical[0],
            'workspaces': descriptors, 'reasons': sorted(set(reasons))}
