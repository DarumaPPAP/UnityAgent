"""Verified UnityArtistCLI Beta artifact installer.

Only the Installer Provider may use this module. The source is an immutable
release tag and the archive is accepted only after its SHA-256 sidecar matches.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import os
from typing import Callable, Mapping
from urllib.request import Request, urlopen
import zipfile
import posixpath
import uuid

REPOSITORY = "DarumaPPAP/UnityArtistCLI"
RELEASE_TAG = "v0.0.1-beta"
CONTROL_PLANE_CHANNEL = "0.0.7-beta"
ARCHIVE_NAME = "UnityArtistCLI-host-windows-x64.zip"
DEFAULT_INSTALL_ROOT = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local")) / "UnityArtistCLI/Beta"


class ReleaseInstallError(RuntimeError):
    pass


def _download(url: str, *, timeout_seconds: float = 60.0) -> bytes:
    request = Request(url, headers={"User-Agent": f"UnityAgent-Installer/{CONTROL_PLANE_CHANNEL}"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is built from the fixed release contract.
        return response.read()


def _expected_sha256(sidecar: bytes) -> str:
    token = sidecar.decode("utf-8").strip().split()[0].lower()
    if len(token) != 64 or any(char not in "0123456789abcdef" for char in token):
        raise ReleaseInstallError("release SHA-256 sidecar is malformed")
    return token


def _archive_executable(archive: bytes) -> bytes:
    """Read exactly one executable without extracting untrusted archive paths."""
    candidates: list[zipfile.ZipInfo] = []
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        for member in package.infolist():
            normalized = posixpath.normpath(member.filename.replace("\\", "/"))
            if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
                raise ReleaseInstallError("release archive contains a path escape")
            if not member.is_dir() and Path(normalized).name == "unity-artist.exe":
                candidates.append(member)
        if len(candidates) != 1:
            raise ReleaseInstallError("release archive must contain exactly one unity-artist.exe")
        return package.read(candidates[0])


def install_plan(
    plan: Mapping[str, object],
    *,
    download_fn: Callable[[str], bytes] = _download,
    install_root: str | Path | None = None,
) -> dict[str, object]:
    """Apply a Control Plane-approved plan and return structured result facts."""
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ReleaseInstallError("approved setup plan has no actions")
    root = Path(install_root or plan.get("install_root") or DEFAULT_INSTALL_ROOT).expanduser().resolve(strict=False)
    release_base = f"https://github.com/{REPOSITORY}/releases/download/{RELEASE_TAG}"
    entries: list[dict[str, object]] = []
    for action in actions:
        if not isinstance(action, Mapping):
            raise ReleaseInstallError("approved setup plan contains a malformed action")
        product = str(action.get("product") or "")
        action_name = str(action.get("action") or "")
        if product == "official_unity_cli":
            if action_name == "verify":
                entries.append({
                    "product": product,
                    "status": "verified",
                    "version": action.get("version"),
                    "location": action.get("location"),
                    "source": "PATH",
                    "sha256": None,
                })
                continue
            entries.append({
                "product": product,
                "status": "unavailable",
                "version": None,
                "location": None,
                "source": "Unity Hub / official Unity installation",
                "sha256": None,
            })
            continue
        if product != "unity_artist_cli":
            raise ReleaseInstallError(f"unsupported install product: {product}")
        if action_name == "verify":
            location = action.get("location") or str(root / "unity-artist.exe")
            entries.append({
                "product": product,
                "status": "verified",
                "version": RELEASE_TAG.removeprefix("v"),
                "location": location,
                "source": f"github:{REPOSITORY}@{RELEASE_TAG}",
                "sha256": None,
            })
            continue
        if action_name != "install_then_verify":
            raise ReleaseInstallError(f"unsupported installer action: {action_name}")

        archive_url = f"{release_base}/{ARCHIVE_NAME}"
        sidecar_url = f"{archive_url}.sha256"
        archive = download_fn(archive_url)
        expected = _expected_sha256(download_fn(sidecar_url))
        actual = hashlib.sha256(archive).hexdigest()
        if actual != expected:
            raise ReleaseInstallError("release archive SHA-256 does not match its sidecar")

        payload = _archive_executable(archive)
        root.mkdir(parents=True, exist_ok=True)
        staged = root / f".unity-artist.exe.staged-{uuid.uuid4().hex}"
        staged.write_bytes(payload)
        target = root / "unity-artist.exe"
        os.replace(staged, target)
        entries.append({
            "product": product,
            "status": "installed",
            "version": RELEASE_TAG.removeprefix("v"),
            "location": str(root / "unity-artist.exe"),
            "source": archive_url,
            "sha256": f"sha256:{actual}",
        })

    status = "passed" if all(str(entry["status"]) in {"installed", "verified"} for entry in entries) else "unavailable"
    channel = str(plan.get("channel") or CONTROL_PLANE_CHANNEL)
    return {
        "schema_version": "1.0",
        "operation": "apply",
        "status": status,
        "project_root": str(plan.get("project_root") or ""),
        "channel": channel,
        "plan_id": plan.get("plan_id"),
        "entries": entries,
        "install_receipt": {
            "schema_version": "1.0",
            "receipt_id": f"receipt-{plan.get('plan_id') or 'unknown'}",
            "run_id": "pending",
            "project_root": str(plan.get("project_root") or ""),
            "channel": channel,
            "entries": entries,
            "verified_at": "1970-01-01T00:00:00+00:00",
            "evidence_refs": [],
        },
    }
