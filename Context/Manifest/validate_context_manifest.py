#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]


def _validate_project_fact_freshness(document: dict) -> None:
    attempt = int(document["attempt"])
    previous = document.get("previous_manifest_ref")
    if attempt > 1 and not previous:
        raise ValueError("retry Context Manifest requires previous_manifest_ref")
    if attempt == 1 and previous is not None:
        raise ValueError("attempt 1 must not declare previous_manifest_ref")
    for index, fact in enumerate(document.get("project_facts", []) or []):
        observed = int(fact["observed_at_attempt"])
        freshness = fact["freshness"]
        checked = int(freshness["checked_at_attempt"])
        status = str(freshness["status"])
        if observed > attempt:
            raise ValueError(f"project_facts[{index}] observation cannot come from a future attempt")
        if checked < observed or checked > attempt:
            raise ValueError(f"project_facts[{index}] checked_at_attempt is outside valid attempt history")
        if status == "current" and checked != attempt:
            raise ValueError(f"project_facts[{index}] current fact must be checked at current attempt")


def validate(path: Path) -> None:
    schema_path = ROOT / "Context/Manifest/context-manifest.schema.yaml"
    context_schema_path = ROOT / "Context/Contracts/materialized-context-view.schema.yaml"
    project_fact_schema_path = ROOT / "Context/Contracts/project-fact-observation.schema.yaml"
    fingerprint_schema_path = ROOT / "Context/Contracts/context-fingerprint.schema.yaml"
    definition_schema_path = ROOT / "Persistence/Contracts/definition-fingerprint.schema.yaml"
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    context_schema = yaml.safe_load(context_schema_path.read_text(encoding="utf-8"))
    project_fact_schema = yaml.safe_load(project_fact_schema_path.read_text(encoding="utf-8"))
    fingerprint_schema = yaml.safe_load(fingerprint_schema_path.read_text(encoding="utf-8"))
    definition_schema = yaml.safe_load(definition_schema_path.read_text(encoding="utf-8"))
    store = {
        "urn:unityagent:context:materialized-context-view": context_schema,
        "urn:unityagent:context:project-fact-observation": project_fact_schema,
        "urn:unityagent:context:context-fingerprint": fingerprint_schema,
        "urn:unityagent:persistence:definition-fingerprint": definition_schema,
    }
    resolver = RefResolver.from_schema(schema, store=store)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, resolver=resolver).validate(document)
    _validate_project_fact_freshness(document)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    validate(args.manifest)
    print("Context manifest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
