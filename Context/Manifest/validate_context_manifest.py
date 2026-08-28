#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]

def validate(path: Path) -> None:
    schema_path = ROOT / "Context/Manifest/context-manifest.schema.yaml"
    context_schema_path = ROOT / "Context/Contracts/materialized-context-view.schema.yaml"
    fingerprint_schema_path = ROOT / "Context/Contracts/context-fingerprint.schema.yaml"
    definition_schema_path = ROOT / "Persistence/Contracts/definition-fingerprint.schema.yaml"
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    context_schema = yaml.safe_load(context_schema_path.read_text(encoding="utf-8"))
    fingerprint_schema = yaml.safe_load(fingerprint_schema_path.read_text(encoding="utf-8"))
    definition_schema = yaml.safe_load(definition_schema_path.read_text(encoding="utf-8"))
    store = {
        "../Contracts/materialized-context-view.schema.yaml": context_schema,
        "context-fingerprint.schema.yaml": fingerprint_schema,
        "../../Persistence/Contracts/definition-fingerprint.schema.yaml": definition_schema,
    }
    resolver = RefResolver.from_schema(schema, store=store)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, resolver=resolver).validate(document)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    validate(args.manifest)
    print("Context manifest: OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
