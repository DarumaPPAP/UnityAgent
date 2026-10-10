#!/usr/bin/env python3
"""既存Import GateでCatalogとDevelopment / Pinned Hub Sourceを読取専用検証する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unityagent.runtime.reference_implementation.catalog_import_gate import CatalogImportError, build_import_plan
CATALOG_PATH = ROOT / "src/unityagent/runtime/reference_implementation/subagent-catalog.yaml"
LOCK_PATH = ROOT / "src/unityagent/runtime/distribution/subagent-sources.lock.json"
HUB_REPOSITORY = "DarumaPPAP/UnitySubAgentHub"
EXPORTER = "Tests/Hub/export_agent_snapshot.py"
EXPORTERS = ("Hub/Tools/export_snapshot.py", EXPORTER)


def validate_hub_source(
    hub_root: Path,
    source_mode: str,
    *,
    lock_path: Path = LOCK_PATH,
    catalog_path: Path = CATALOG_PATH,
) -> dict:
    """指定Commitだけを隔離展開し、既存Exporter / Import Gateへ渡す。"""
    if source_mode not in {"development", "pinned"}:
        raise ValueError("source mode must be development or pinned")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    hub = lock.get("hub") if isinstance(lock, dict) else None
    if not isinstance(hub, dict) or hub.get("repository") != HUB_REPOSITORY:
        raise ValueError("source lock must name DarumaPPAP/UnitySubAgentHub")
    locked_commit = hub.get("commit")
    if not isinstance(locked_commit, str) or re.fullmatch(r"[0-9a-f]{40}", locked_commit) is None:
        raise ValueError("source lock must contain a full immutable Hub commit")
    locked_exporter = hub.get("snapshot_exporter", EXPORTER)
    if locked_exporter not in EXPORTERS:
        raise ValueError("source lock contains an unknown Hub snapshot exporter")
    hub_root = hub_root.resolve()

    def git(*args: str) -> str:
        result = subprocess.run(["git", "-C", str(hub_root), *args], capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f"Hub Git source unavailable: {result.stderr.strip()}")
        return result.stdout.strip()

    if Path(git("rev-parse", "--show-toplevel")).resolve() != hub_root:
        raise ValueError("--hub-root must be the Hub repository root")
    commit = git("rev-parse", "--verify", ("HEAD" if source_mode == "development" else locked_commit) + "^{commit}")
    if source_mode == "pinned" and commit != locked_commit:
        raise ValueError("resolved Hub commit differs from source lock")
    # CheckoutせずCommitを展開し、未Commit変更をSnapshotへ混入させない。
    with tempfile.TemporaryDirectory(prefix="unityagent-hub-contract-") as directory:
        temporary = Path(directory)
        source = temporary / "source"
        source.mkdir()
        archive = temporary / "source.tar"
        with archive.open("wb") as stream:
            result = subprocess.run(
                ["git", "-C", str(hub_root), "archive", "--format=tar", commit],
                stdout=stream, stderr=subprocess.PIPE, text=True,
            )
        if result.returncode:
            raise ValueError(f"Hub archive failed: {result.stderr.strip()}")
        with tarfile.open(archive) as tree:
            tree.extractall(source, filter="data")
        # 移行中は既知の二配置だけを許可し、固定SourceではLockの配置を厳守する。
        available = [path for path in EXPORTERS if (source / path).is_file()]
        if len(available) != 1:
            raise ValueError("Hub source must contain exactly one known snapshot exporter")
        exporter = available[0]
        if source_mode == "pinned" and exporter != locked_exporter:
            raise ValueError("pinned Hub exporter differs from source lock")
        snapshot = temporary / "snapshot.yaml"
        result = subprocess.run(
            [sys.executable, str(source / exporter), "--repo-root", str(source), "--output", str(snapshot)],
            cwd=source, capture_output=True, text=True,
        )
        if result.returncode:
            raise ValueError(f"Hub snapshot export failed: {result.stderr.strip() or result.stdout.strip()}")
        payload = snapshot.read_bytes()
    plan = build_import_plan(
        payload,
        source_ref=f"github://{HUB_REPOSITORY}/{commit}/{exporter}",
        expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
        current_catalog=None,
        current_catalog_bytes=catalog_path.read_bytes(),
        current_catalog_ref=catalog_path.resolve().relative_to(ROOT).as_posix()
        if catalog_path.resolve().is_relative_to(ROOT) else str(catalog_path),
    )
    plan["source"].update(mode=source_mode, repository=HUB_REPOSITORY, commit=commit, locked_commit=locked_commit)
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub-root", type=Path, help="local Hub Git checkout; no network fetch or checkout performed")
    parser.add_argument("--source-mode", choices=("development", "pinned"), help="HEAD or immutable Source Lock commit")
    args = parser.parse_args(argv)
    if bool(args.hub_root) != bool(args.source_mode):
        parser.error("--hub-root and --source-mode must be supplied together")
    try:
        if args.hub_root:
            plan = validate_hub_source(args.hub_root, args.source_mode)
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0 if plan["status"] == "no_op" and not plan["apply"]["catalog_write_performed"] else 1
        payload = CATALOG_PATH.read_bytes()
        plan = build_import_plan(
            payload,
            source_ref="checked-in://src/unityagent/runtime/reference_implementation/subagent-catalog.yaml",
            expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
            current_catalog=None,
            current_catalog_bytes=payload,
            current_catalog_ref="src/unityagent/runtime/reference_implementation/subagent-catalog.yaml",
        )
        if plan["status"] != "no_op" or plan["apply"]["catalog_write_performed"]:
            raise CatalogImportError("checked_in_catalog_not_noop", "checked-in catalog did not pass as a read-only no-op")
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        if args.hub_root:
            print(json.dumps({"status": "rejected", "error": {"code": getattr(exc, "code", "hub_source_error"), "message": str(exc)}}, ensure_ascii=False, indent=2))
            return 1
        print(f"Catalog Import Gate validation failed: {exc}")
        return 1
    print("Catalog Import Gate validation passed (checked-in catalog is a read-only no-op).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
