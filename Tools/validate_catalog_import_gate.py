#!/usr/bin/env python3
"""チェックイン済みCatalogがOffline Import GateをNo-opで通過することを検証する。"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.ReferenceImplementation.catalog_import_gate import CatalogImportError, build_import_plan
CATALOG_PATH = ROOT / "Runtime/ReferenceImplementation/subagent-catalog.yaml"


def main() -> int:
    try:
        payload = CATALOG_PATH.read_bytes()
        plan = build_import_plan(
            payload,
            source_ref="checked-in://Runtime/ReferenceImplementation/subagent-catalog.yaml",
            expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
            current_catalog=None,
            current_catalog_bytes=payload,
            current_catalog_ref="Runtime/ReferenceImplementation/subagent-catalog.yaml",
        )
        if plan["status"] != "no_op" or plan["apply"]["catalog_write_performed"]:
            raise CatalogImportError("checked_in_catalog_not_noop", "checked-in catalog did not pass as a read-only no-op")
    except (OSError, ValueError, CatalogImportError) as exc:
        print(f"Catalog Import Gate validation failed: {exc}")
        return 1
    print("Catalog Import Gate validation passed (checked-in catalog is a read-only no-op).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
