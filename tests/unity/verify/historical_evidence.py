"""Integrity checks for archived observations; these never certify current Unity runs."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "ci/evidence/artist/historical/index.json"


def validate_historical_evidence(path: Path | None = None) -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    if index.get("current_editor_status") != "BLOCKED_NOT_RUN" or index.get("current_observation") != "not_observed":
        raise ValueError("Historical records cannot certify current Editor validation")
    records = index["records"]
    selected = records if path is None else [row for row in records if ROOT / row["path"] == path]
    if not selected:
        raise ValueError(f"Historical record is not indexed: {path}")
    for row in selected:
        archived = ROOT / row["path"]
        if row.get("classification") != "historical" or row.get("current_observation") != "not_observed":
            raise ValueError(f"Incorrect historical classification: {archived}")
        if hashlib.sha256(archived.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Preserved historical record bytes changed: {archived}")
    if path is None:
        actual = {str(p.relative_to(ROOT)) for p in INDEX.parent.iterdir() if p.is_file() and p != INDEX}
        if actual != {row["path"] for row in records}:
            raise ValueError("Historical evidence inventory differs from its preservation index")


def validate_preserved_assets() -> None:
    audit = json.loads((ROOT / "docs/migration/consolidation/p4-path-map.json").read_text(encoding="utf-8"))
    fixture = ROOT / "tests/fixtures/legacy"
    actual = {str(p.relative_to(fixture)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in fixture.rglob("*") if p.is_file()}
    if actual != audit["legacy_fixture_sha256"]:
        raise ValueError("Frozen legacy fixture inventory or byte hashes changed")
    tag = subprocess.check_output(["git", "rev-parse", "refs/tags/v1.1.1"], cwd=ROOT, text=True).strip()
    if tag != audit["immutable_tag"]["object"]:
        raise ValueError("Frozen legacy tag changed")
    for location, project in audit["preserved_unity_projects"].items():
        for relative, digest in project["sha256"].items():
            path = ROOT / location / relative
            if relative in {"Packages/manifest.json", "Packages/packages-lock.json"}:
                data = json.loads(path.read_text(encoding="utf-8"))
                local = data["dependencies"]["com.darumappap.artist-subagent"]
                if isinstance(local, dict):
                    local = local["version"]
                if not local.startswith("file:") or (path.parent / local[5:]).resolve() != ROOT / "Packages/com.darumappap.artist-subagent":
                    raise ValueError(f"Broken local UPM dependency: {path}")
                # Reconstruct the original local path; all other project content must be preserved.
                original = path.read_text(encoding="utf-8").replace(local, "file:../../../Packages/com.darumappap.artist-subagent").encode()
                if hashlib.sha256(original).hexdigest() != digest:
                    raise ValueError(f"Unity fixture manifest content changed: {path}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Unity fixture content changed: {path}")
