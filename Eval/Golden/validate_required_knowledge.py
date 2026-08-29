#!/usr/bin/env python3
"""Validate canonical Task Contract required_knowledge routing completeness."""

from __future__ import annotations

from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "Context" / "Selection" / "context-catalog.yaml"
MATERIALIZER_PATH = ROOT / "Context" / "Assembly" / "materialize_context.py"


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping: {path}")
    return data


def main() -> int:
    errors: list[str] = []
    try:
        catalog = load_yaml(CATALOG_PATH)
        materializer_text = MATERIALIZER_PATH.read_text(encoding="utf-8")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Required Knowledge validation failed:\n- {exc}")
        return 1

    covered = 0
    for route_id, route in (catalog.get("routes", {}) or {}).items():
        if not isinstance(route, dict):
            continue
        contract_path = route.get("task_contract")
        if not contract_path:
            errors.append(f"{route_id}: canonical task_contract is required.")
            continue
        try:
            contract = load_yaml(ROOT / str(contract_path))
        except Exception as exc:  # noqa: BLE001 - report exact route/contract failure.
            errors.append(f"{route_id}: failed to load Task Contract: {exc}")
            continue
        required = [str(value) for value in contract.get("required_knowledge", []) or []]
        if not required:
            continue
        covered += 1
        selection = route.get("knowledge_selection")
        if selection not in {"required", "required_when_domain_matches", "optional"}:
            errors.append(f"{route_id}: required_knowledge requires explicit knowledge_selection; found {selection!r}.")
        if any(not value.strip() for value in required):
            errors.append(f"{route_id}: required_knowledge contains an empty selector.")

    for marker in (
        "knowledge_refs: list[str] | None",
        'role": "knowledge"',
        'route.get("knowledge_selection") == "required_when_domain_matches"',
        'unresolved.append("knowledge_selection")',
    ):
        if marker not in materializer_text:
            errors.append(f"Canonical Context materializer missing knowledge handling marker: {marker}")

    if covered == 0:
        errors.append("No canonical Task Contract with required_knowledge was found; completeness check is ineffective.")

    if errors:
        print("Required Knowledge validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Required Knowledge validation passed: {covered} route contracts declare machine-readable knowledge requirements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
