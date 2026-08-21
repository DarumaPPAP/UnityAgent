#!/usr/bin/env python3
"""Validate Task Contract required_knowledge routing completeness."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / ".ai" / "context-index.yaml"
RUNTIME_PATH = ROOT / "Tools" / "ContextManifest" / "context_manifest_runtime.py"


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def main() -> int:
    errors: list[str] = []
    try:
        index = load_yaml(INDEX_PATH)
        runtime_text = RUNTIME_PATH.read_text(encoding="utf-8")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Required Knowledge validation failed:\n- {exc}")
        return 1

    covered = 0
    for route_key, route in (index.get("routes", {}) or {}).items():
        if not isinstance(route, dict):
            continue
        contract_path = route.get("task_contract")
        if not contract_path:
            continue
        try:
            contract = load_yaml(ROOT / str(contract_path))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{route_key}: failed to load Task Contract: {exc}")
            continue
        required = [str(value) for value in contract.get("required_knowledge", []) or []]
        if not required:
            continue
        covered += 1
        selection = route.get("knowledge_selection")
        if selection is not None and selection not in {"required", "required_when_domain_matches", "optional"}:
            errors.append(
                f"{route.get('id', route_key)}: unsupported knowledge_selection value {selection}."
            )
        if any(not value.strip() for value in required):
            errors.append(f"{route.get('id', route_key)}: required_knowledge contains an empty selector.")

    for marker in (
        "request.get('knowledge'",
        "'knowledge': {'loaded': knowledge}",
        "stable_node_id('knowledge'",
    ):
        if marker not in runtime_text:
            errors.append(f"Context Manifest Runtime missing knowledge handling marker: {marker}")

    if covered == 0:
        errors.append("No Task Contract with required_knowledge was found; completeness check is ineffective.")

    if errors:
        print("Required Knowledge validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Required Knowledge validation passed: {covered} route contracts declare machine-readable knowledge requirements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
