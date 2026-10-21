"""同じ物理Projectへの協調実行をHost共有のOSロックで排他する。"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path
from typing import Iterator

from unityagent.runtime.tooling.environment.project_identity import canonicalize_project_root


class ProjectLeaseBusy(RuntimeError):
    """別の生存する所有者がProjectの実行権を保持している。"""


def _default_lock_root() -> Path:
    # Process環境を変更しても別namespaceへ逃げないようOSのユーザー領域を使う。
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(260)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x001C, None, 0, buffer)
        if result != 0 or not buffer.value:
            raise OSError('OS local application data directory is unavailable')
        base = Path(buffer.value)
    else:
        import pwd
        base = Path(pwd.getpwuid(os.getuid()).pw_dir) / '.cache'
    return base / 'UnityAgent/ProjectLeases'


@contextmanager
def acquire_project_lease(
    project_root: str | Path, *, owner: str, lock_root: str | Path | None = None,
) -> Iterator[dict[str, str | int]]:
    """非blocking取得。TTLによる奪取・待機中の自動再試行は行わない。

    Handleを実行とEvidence保存まで保持する。Process終了時はOSが解放する。
    非協調Editor・ユーザー手動編集の保護は既存のbinding/revision gateが担う。
    """
    project = Path(project_root).expanduser().resolve(strict=True)
    if not project.is_dir():
        raise ValueError('lease requires an existing Project directory')
    identity = canonicalize_project_root(project)
    with _acquire_identity(identity, owner=owner, lock_root=lock_root) as record:
        yield {'project_identity': identity, **record}


@contextmanager
def acquire_host_claims(claims, *, owner, lock_root=None):
    """Project Run取得後にだけ呼ぶ。正規化順・非blockingで共用Host資源を排他する。"""
    if not isinstance(claims, (list, tuple)):
        raise ValueError('Host resource claims must be a list')
    normalized = []
    for value in claims:
        if not isinstance(value, str) or not value.strip() or '\x00' in value:
            raise ValueError('Host resource claim is invalid')
        value = value.strip().replace('\\', '/').casefold().rstrip('/')
        if '..' in value.split('/') or not value:
            raise ValueError('Host resource claim is not confined')
        normalized.append(value)
    with ExitStack() as stack:
        records = []
        for claim in sorted(set(normalized)):
            record = stack.enter_context(_acquire_identity('host-resource:' + claim, owner=owner,
                lock_root=lock_root, identity_key='resource_identity'))
            records.append({'resource_identity': claim, **record})
        yield records


@contextmanager
def _acquire_identity(identity, *, owner, lock_root=None, identity_key='project_identity'):
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError('lease owner must be a non-empty run identity')
    digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()
    directory = Path(lock_root) if lock_root is not None else _default_lock_root()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(directory / f'{digest}.lock', os.O_RDWR | os.O_CREAT, 0o600)
    acquired = False
    try:
        # Windowsのbyte range lock用。ロックファイルは削除せずinodeの分裂を防ぐ。
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b'\0')
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise ProjectLeaseBusy('Project is owned by another active UnityAgent run') from exc
            raise
        record = {'owner': owner, 'process_id': os.getpid()}
        persisted = {identity_key: identity, **record}
        payload = json.dumps(persisted, ensure_ascii=False).encode('utf-8')
        os.lseek(descriptor, 1, os.SEEK_SET)
        os.write(descriptor, payload)
        os.ftruncate(descriptor, len(payload) + 1)
        yield record
    finally:
        try:
            if acquired:
                if os.name == 'nt':
                    import msvcrt
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
