#!/usr/bin/env python3
"""Offline SubAgent Catalog Snapshotから読取専用Import Planを作成する。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.ReferenceImplementation.catalog_import_gate import CatalogImportError, build_import_plan
DEFAULT_CATALOG = ROOT / "Runtime/ReferenceImplementation/subagent-catalog.yaml"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True, help="offline Hub snapshot file")
    parser.add_argument("--source-ref", required=True, help="immutable source reference recorded in the plan")
    parser.add_argument("--expected-sha256", required=True, help="SHA-256 for the exact snapshot bytes")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="current UnityAgent catalog")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        snapshot_bytes = args.snapshot.read_bytes()
        catalog_bytes = args.catalog.read_bytes()
        plan = build_import_plan(
            snapshot_bytes,
            source_ref=args.source_ref,
            expected_sha256=args.expected_sha256,
            current_catalog=None,
            current_catalog_bytes=catalog_bytes,
            current_catalog_ref=args.catalog.resolve().relative_to(ROOT.resolve()).as_posix()
            if args.catalog.resolve().is_relative_to(ROOT.resolve())
            else str(args.catalog.resolve()),
        )
    except CatalogImportError as exc:
        error = {
            "kind": "subagent_catalog_import_plan",
            "schema_version": "1.0",
            "status": "rejected",
            "error": {"code": exc.code, "message": str(exc)},
        }
        print(json.dumps(error, ensure_ascii=False, indent=2))
        return 1
    except (OSError, ValueError) as exc:
        error = {
            "kind": "subagent_catalog_import_plan",
            "schema_version": "1.0",
            "status": "rejected",
            "error": {"code": "input_error", "message": str(exc)},
        }
        print(json.dumps(error, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=False))
    return 1 if plan["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
