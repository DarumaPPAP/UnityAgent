"""Conservative cross-process Project lease for UnityAgent Runtime.

Never treat an Orchestration batch plan as an execution grant. Only the
Runtime may own this lock. A stale lease is NOT automatically reclaimed:
manual recovery must establish the Unity process is no longer running.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class ProjectLeaseUnavailable(RuntimeError):
    """A competing or unverifiable Project lease prevented execution."""


class ProjectLeaseError(RuntimeError):
    """Lease storage or integrity could not be verified."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lease_directory(project_root: str | Path, lease_root: Path | None = None) -> tuple[Path, str]:
    root = Path(project_root).expanduser()
    if not root.is_absolute() or not str(root).strip():
        raise ProjectLeaseError("a bound absolute Project path is required")
    project = str(root.resolve(strict=False)).replace("\\", "/").casefold().rstrip("/")
    if not project:
        raise ProjectLeaseError("Project path is empty")
    root_value = lease_root
    if root_value is None:
        base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
        root_value = (Path(base) if base else Path.home() / ".cache") / "UnityAgent" / "RuntimeLeases"
    storage = Path(root_value).expanduser()
    if not storage.is_absolute():
        raise ProjectLeaseError("lease storage must be an absolute path")
    digest = hashlib.sha256(project.encode("utf-8")).hexdigest()
    return storage / digest, project


def _reject_links(directory: Path) -> None:
    for part in (directory, *directory.parents):
        if part.is_symlink():
            raise ProjectLeaseError("lease storage contains a symlink")


class RuntimeProjectLease:
    """Atomic, exclusive Project lease. No automatic stale-lock stealing.

    A separate user-level directory coordinates Editor tasks across processes.
    Read-only file inspection deliberately bypasses this lock to preserve Fast Path.
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        lease_root: Path | None = None,
        heartbeat_seconds: float = 10.0,
    ) -> None:
        if heartbeat_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        self.directory, self.project = _lease_directory(project_root, lease_root)
        self.token = uuid4().hex
        self.heartbeat_seconds = heartbeat_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._owned = False

    def __enter__(self) -> RuntimeProjectLease:
        _reject_links(self.directory.parent)
        try:
            self.directory.parent.mkdir(parents=True, exist_ok=True)
            _reject_links(self.directory.parent)
            self.directory.mkdir()
        except FileExistsError as exc:
            raise ProjectLeaseUnavailable("Project is already leased; do not launch another Editor") from exc
        except OSError as exc:
            raise ProjectLeaseError("cannot create Project lease") from exc
        self._owned = True
        try:
            self._write_record()
            self._thread = threading.Thread(target=self._pulse, name="UnityAgentProjectLease", daemon=True)
            self._thread.start()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def _write_record(self) -> None:
        if not self._owned or self.directory.is_symlink():
            raise ProjectLeaseError("Project lease ownership was lost")
        data = {
            "schema_version": "1.0",
            "project_root": self.project,
            "token": self.token,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "heartbeat_at": _utc_now(),
        }
        payload = json.dumps(data, sort_keys=True) + "\n"
        target = self.directory / "lease.json"
        if target.exists() or target.is_symlink():
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
                if existing.get("token") != self.token:
                    raise ProjectLeaseError("Project lease token mismatch")
            except (OSError, ValueError) as exc:
                raise ProjectLeaseError("Project lease metadata invalid") from exc
        temporary = self.directory / ("." + self.token + ".tmp")
        with temporary.open("x", encoding="utf-8") as writer:
            writer.write(payload)
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _pulse(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                self._write_record()
            except (OSError, ProjectLeaseError):
                # Keep directory locked if an owner cannot be re-established.
                # Runtime never steals or deletes an unverified lock.
                return

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.heartbeat_seconds + 1)
        if not self._owned:
            return
        self._owned = False
        record = self.directory / "lease.json"
        try:
            _reject_links(self.directory)
            if record.is_symlink():
                raise ProjectLeaseError("lease metadata is a symlink")
            data = json.loads(record.read_text(encoding="utf-8"))
            if data.get("token") != self.token or data.get("pid") != os.getpid():
                raise ProjectLeaseError("refusing to release another process's lease")
            record.unlink()
            self.directory.rmdir()
        except (OSError, ValueError) as error:
            raise ProjectLeaseError("Project lease release requires manual inspection") from error
