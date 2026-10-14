#!/usr/bin/env python3
"""同居SubAgentの実ManifestをSnapshot化し、UnityAgent Catalogと厳密に照合する。

Runtime Migration Gate。オンラインHub参照・Repository Mutation・Agent実行は禁止。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "subagent/tools"))
sys.path.insert(0, str(ROOT / "src"))

from export_snapshot import export_hub_snapshot
from unityagent.runtime.reference_implementation.catalog_import_gate import (
    CatalogImportError,
    build_import_plan,
)

CATALOG_PATH = ROOT / "src/unityagent/runtime/reference_implementation/subagent-catalog.yaml"


def validate_local_catalog() -> dict:
    snapshot = export_hub_snapshot(ROOT)
    payload = yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True, width=1000).encode("utf-8")
    catalog = CATALOG_PATH.read_bytes()
    plan = build_import_plan(
        payload,
        source_ref="co-located://subagent/registry.yaml",
        expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
        current_catalog=None,
        current_catalog_bytes=catalog,
        current_catalog_ref=CATALOG_PATH.relative_to(ROOT).as_posix(),
    )
    if plan["status"] != "no_op" or plan["apply"]["catalog_write_performed"]:
        raise CatalogImportError("local_contract_drift",
                                 "co-located SubAgent manifests diverge from UnityAgent Consumer Catalog")
    return plan


def main() -> int:
    try:
        plan = validate_local_catalog()
    except (OSError, ValueError, CatalogImportError, yaml.YAMLError) as exc:
        print("Co-located SubAgent Catalog Gate FAILED: " + str(exc), file=sys.stderr)
        return 1
    print("Co-located SubAgent Catalog Gate PASS: " + plan["source"]["ref"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
