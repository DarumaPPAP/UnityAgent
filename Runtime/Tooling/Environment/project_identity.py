"""Canonical Unity project identity helpers used by Runtime environment discovery."""
from __future__ import annotations

import ntpath
import os
import platform
import re
from pathlib import Path
from typing import Any

PROJECT_MARKERS = ("Assets", "Packages", "ProjectSettings")
PROJECT_VERSION_FILE = Path("ProjectSettings/ProjectVersion.txt")
_EDITOR_VERSION_RE = re.compile(r"^m_EditorVersion:\s*(?P<version>\S+)\s*$", re.MULTILINE)


def canonicalize_project_root(
    project_root: str | os.PathLike[str],
    *,
    platform_name: str | None = None,
    resolve_symlinks: bool = True,
) -> str:
    """Return a stable project-root identity without requiring the path to exist.

    Windows identities are case-folded because filesystem path identity is normally
    case-insensitive there. POSIX identities preserve case. Symlinks are resolved on
    the current POSIX host when requested so equivalent roots compare equal.
    """
    raw = os.fspath(project_root).strip()
    if not raw:
        raise ValueError("project_root must not be blank")

    current_platform = (platform_name or platform.system()).lower()
    if current_platform.startswith("win"):
        normalized = ntpath.normpath(raw.replace("/", "\\"))
        if not ntpath.isabs(normalized):
            normalized = ntpath.abspath(normalized)
        return normalized.replace("\\", "/").casefold()

    path = Path(raw).expanduser()
    if resolve_symlinks:
        path = path.resolve(strict=False)
    else:
        path = Path(os.path.abspath(os.path.normpath(str(path))))
    return path.as_posix()


def same_project_root(
    left: str | os.PathLike[str],
    right: str | os.PathLike[str],
    *,
    platform_name: str | None = None,
) -> bool:
    return canonicalize_project_root(left, platform_name=platform_name) == canonicalize_project_root(
        right, platform_name=platform_name
    )


def read_project_version(project_root: str | os.PathLike[str]) -> str | None:
    version_path = Path(project_root).expanduser() / PROJECT_VERSION_FILE
    try:
        text = version_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    match = _EDITOR_VERSION_RE.search(text)
    return match.group("version") if match else None


def observe_project_identity(project_root: str | os.PathLike[str]) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve(strict=False)
    root_exists = root.is_dir()
    required = {name: (root / name).is_dir() for name in PROJECT_MARKERS}
    project_exists = root_exists and all(required.values())
    if project_exists:
        identity_status = "bound"
    elif root_exists:
        identity_status = "invalid"
    else:
        identity_status = "invalid"

    return {
        "root": canonicalize_project_root(root),
        "exists": project_exists,
        "identity_status": identity_status,
        "unity_version": read_project_version(root),
        "required_paths": {
            "assets": required["Assets"] if root_exists else False,
            "packages": required["Packages"] if root_exists else False,
            "project_settings": required["ProjectSettings"] if root_exists else False,
        },
    }
