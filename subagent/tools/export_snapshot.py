#!/usr/bin/env python3
"""Export a consumer-neutral, static SubAgent Hub catalog snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml

from validate_registry import ROOT, _check_schema_definition, _schema_errors, validate_repository


REGISTRY_PATH = Path("subagent/registry.yaml")
SNAPSHOT_SCHEMA_PATH = Path("subagent/schemas/subagent-catalog-snapshot.schema.json")
MANIFEST_SCHEMA_PATH = Path("subagent/schemas/subagent-manifest.schema.json")


def validate_snapshot(snapshot: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Validate the export envelope and each embedded canonical manifest."""
    errors: list[str] = []
    snapshot_schema = _check_schema_definition(json.loads((root / SNAPSHOT_SCHEMA_PATH).read_text(encoding="utf-8")), str(SNAPSHOT_SCHEMA_PATH), errors)
    manifest_schema = _check_schema_definition(json.loads((root / MANIFEST_SCHEMA_PATH).read_text(encoding="utf-8")), str(MANIFEST_SCHEMA_PATH), errors)
    _schema_errors(snapshot, snapshot_schema, "snapshot", errors)
    entries = snapshot.get("specialists")
    if not isinstance(entries, list):
        return errors
    refs: set[str] = set()
    identities: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        reference = entry.get("manifest_ref")
        manifest = entry.get("manifest")
        if not isinstance(reference, str) or not isinstance(manifest, dict):
            continue
        _schema_errors(manifest, manifest_schema, f"snapshot.specialists[{index}].manifest", errors)
        identity = manifest.get("identity", {}).get("id") if isinstance(manifest.get("identity"), dict) else None
        if not isinstance(identity, str):
            errors.append(f"snapshot.specialists[{index}]: identity.id must be a string")
            continue
        if reference != f"subagent/{identity}/manifest.yaml":
            errors.append(f"snapshot.specialists[{index}]: manifest_ref and identity.id disagree")
        if reference in refs or identity in identities:
            errors.append(f"snapshot.specialists[{index}]: duplicate manifest or specialist identity")
        refs.add(reference)
        identities.add(identity)
    return errors


def export_hub_snapshot(root: Path = ROOT) -> dict[str, Any]:
    """Build a versioned static Snapshot from every indexed manifest."""
    errors = validate_repository(root)
    if errors:
        raise ValueError("Hub registry is invalid:\n" + "\n".join(errors))

    registry = yaml.safe_load((root / REGISTRY_PATH).read_text(encoding="utf-8"))
    specialists = []
    for entry in registry["entries"]:
        reference = entry["manifest"]
        manifest = yaml.safe_load((root / Path(*reference.split("/"))).read_text(encoding="utf-8"))
        specialists.append({"manifest_ref": reference, "manifest": manifest})
    snapshot = {"schema_version": "3.0", "kind": "subagent_catalog_snapshot", "specialists": specialists}
    errors = validate_snapshot(snapshot, root)
    if errors:
        raise ValueError("Hub snapshot is invalid:\n" + "\n".join(errors))
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT, help="repository root to export")
    parser.add_argument("--output", type=Path, help="write the snapshot to this path; stdout when omitted")
    args = parser.parse_args(argv)
    try:
        output = yaml.safe_dump(export_hub_snapshot(args.repo_root.resolve()), sort_keys=False, allow_unicode=True, width=1000)
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"Hub snapshot written: {args.output}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
