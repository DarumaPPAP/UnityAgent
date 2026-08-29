"""Workspace path confinement and deterministic snapshot/change observation."""
from __future__ import annotations
from pathlib import Path, PurePosixPath


class WorkspaceGuardError(ValueError):
    pass


def workspace_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise WorkspaceGuardError(f"workspace does not exist: {path}")
    return path


def normalize_relative_path(value: str) -> str:
    raw = value.replace("\\", "/").strip()
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or ".." in pure.parts:
        raise WorkspaceGuardError(f"unsafe repository-relative path: {value}")
    return pure.as_posix().rstrip("/")


def confined_path(workspace: Path, value: str, *, require_file: bool = False) -> Path:
    relative = normalize_relative_path(value)
    resolved = (workspace / Path(*PurePosixPath(relative).parts)).resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise WorkspaceGuardError(f"path escapes workspace: {value}")
    if require_file and not resolved.is_file():
        raise WorkspaceGuardError(f"file does not exist: {value}")
    return resolved


def snapshot_workspace(workspace: Path, *, excluded_prefixes: tuple[str, ...] = ()) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
        relative = path.relative_to(workspace).as_posix()
        if any(relative == prefix or relative.startswith(prefix.rstrip("/") + "/") for prefix in excluded_prefixes):
            continue
        snapshot[relative] = path.read_bytes()
    return snapshot


def changed_paths(before: dict[str, bytes], after: dict[str, bytes]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
