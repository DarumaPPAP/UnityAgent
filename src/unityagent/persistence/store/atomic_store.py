"""Filesystem primitives for canonical Persistence records.

The caller chooses the store root. Persistence owns the layout below that
root; no source-tree path is implicitly selected.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class PersistenceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def safe_id(value: Any, field: str = "id") -> str:
    text = str(value or "").strip()
    if not ID_RE.fullmatch(text):
        raise PersistenceError("invalid_identifier", f"{field} is not a safe identifier")
    return text


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


@contextmanager
def exclusive_file_lock(path: Path, *, timeout_seconds: float = 30.0):
    """Hold a small cross-process advisory lock for a Persistence operation.

    The lock file is intentionally retained.  Its contents are not authority;
    the OS byte-range lock is the authority, so a crashed process does not
    leave a stale lock marker behind that can block future runs.
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
            os.fsync(stream.fileno())
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise PersistenceError("lock_timeout", f"timed out acquiring Persistence lock: {lock_path}") from exc
                    time.sleep(0.01)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PersistenceError("record_not_found", f"record not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PersistenceError("record_corrupt", f"cannot read JSON record {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PersistenceError("record_corrupt", f"record must be an object: {path}")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the temporary basename deliberately short.  Windows legacy path
    # handling reports ERROR_PATH_NOT_FOUND when the temporary name pushes a
    # long-but-valid workspace path over MAX_PATH, even when the final record
    # name itself still fits.  The directory is already bound to this target,
    # so the target basename does not need to be repeated in the temp name.
    fd, temp_name = tempfile.mkstemp(prefix=".p-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(canonical_json(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_immutable_json(path: Path, value: dict[str, Any]) -> bool:
    """Create once. Same content is idempotent; different content is blocked."""
    if path.exists():
        existing = read_json(path)
        if canonical_json(existing) == canonical_json(value):
            return False
        raise PersistenceError("immutable_record_conflict", f"immutable record already exists with different content: {path}")
    atomic_write_json(path, value)
    return True


def relative_ref(root: Path, path: Path) -> str:
    root = root.resolve()
    path = path.resolve()
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise PersistenceError("path_escape_forbidden", f"path escapes Persistence root: {path}") from exc


def resolve_ref(root: Path, ref: str) -> Path:
    root = root.resolve()
    candidate = (root / ref).resolve()
    if candidate != root and root not in candidate.parents:
        raise PersistenceError("path_escape_forbidden", f"Persistence ref escapes root: {ref}")
    return candidate
