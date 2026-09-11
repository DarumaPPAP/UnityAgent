#!/usr/bin/env python3
"""Validate the product-facing UnityAgent five-layer dependency contract."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = Path("Specs/unityagent-layer-contract.yaml")
EXPECTED_LAYERS = {
    "entry",
    "control_plane",
    "capability_orchestration",
    "provider_layer",
    "evidence_state",
}
EXPECTED_EDGES = {
    ("entry", "control_plane", "request"),
    ("entry", "evidence_state_read", "read_only_projection"),
    ("control_plane", "capability_orchestration", "semantic_handoff"),
    ("control_plane", "evidence_state", "run_and_evidence_persistence"),
    ("capability_orchestration", "provider_layer", "resolved_dispatch"),
    ("capability_orchestration", "evidence_state", "evidence_requirements"),
    ("provider_layer", "evidence_state", "structured_result_capture"),
}
FORBIDDEN_ENTRY_TEXT = ("unity artist", "unity-artist")
CANONICAL_VERSION = "0.0.2-beta"


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping: {path}")
    return value


def validate(root: Path = ROOT) -> list[str]:
    contract = _load(root / CONTRACT_PATH)
    errors: list[str] = []
    if contract.get("schema_version") != "1.0":
        errors.append("layer contract schema_version must be 1.0")
    layers = contract.get("layers")
    if not isinstance(layers, dict) or set(layers) != EXPECTED_LAYERS:
        errors.append(f"layer set must be exactly {sorted(EXPECTED_LAYERS)}")
        layers = layers if isinstance(layers, dict) else {}
    for layer_id in EXPECTED_LAYERS:
        layer = layers.get(layer_id)
        if not isinstance(layer, dict):
            errors.append(f"missing layer definition: {layer_id}")
            continue
        for field in ("title", "owner", "responsibilities", "allowed_dependencies", "forbidden_dependencies"):
            if field not in layer:
                errors.append(f"{layer_id} missing {field}")
        if not isinstance(layer.get("responsibilities"), list) or not layer["responsibilities"]:
            errors.append(f"{layer_id}.responsibilities must be non-empty")

    graph = contract.get("dependency_graph") or []
    actual_edges = {
        (str(item.get("from")), str(item.get("to")), str(item.get("mode")))
        for item in graph
        if isinstance(item, dict)
    }
    if actual_edges != EXPECTED_EDGES:
        errors.append("dependency_graph does not match the fixed five-layer direction")

    if "provider_layer" not in (layers.get("entry", {}).get("forbidden_dependencies") or []):
        errors.append("Entry Layer must forbid direct Provider dependency")
    if "provider_layer_direct" not in (layers.get("control_plane", {}).get("forbidden_dependencies") or []):
        errors.append("Control Plane must forbid direct Provider dependency")
    invariants = contract.get("invariants") or {}
    for key in ("no_entry_to_provider", "no_semantic_provider_selection", "evidence_is_recorded_by_all_layers"):
        if invariants.get(key) is not True:
            errors.append(f"invariant must be true: {key}")

    for relative in ("Runtime/Contracts/entry-request.schema.yaml", "Runtime/Contracts/toolchain-setup-request.schema.yaml", "Runtime/Contracts/install-receipt.schema.yaml", "Packages/com.darumappap.unity-agent/package.json"):
        if not (root / relative).is_file():
            errors.append(f"cross-layer contract is missing: {relative}")

    package_path = root / "Packages/com.darumappap.unity-agent/package.json"
    if package_path.is_file():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"UnityAgent UPM package metadata is invalid: {exc}")
        else:
            if package.get("name") != "com.darumappap.unity-agent":
                errors.append("UnityAgent UPM package name is not canonical")
            if package.get("version") != CANONICAL_VERSION:
                errors.append(f"UnityAgent UPM package version is not {CANONICAL_VERSION}")
        for path in sorted(package_path.parent.glob("Editor/*.cs")):
            text = path.read_text(encoding="utf-8").casefold()
            if "unity-artist" in text or "unity artist" in text:
                errors.append(f"Unity UI Entry must not invoke UnityArtistCLI directly: {path.relative_to(root)}")
            if "filename = \"unity\"" in text:
                errors.append(f"Unity UI Entry must not invoke Official Unity CLI directly: {path.relative_to(root)}")
            if "filename = \"codex\"" in text or "codex plugin marketplace" in text or "codex plugin add" in text:
                errors.append(f"Unity UI Entry must not invoke Codex Plugin commands directly: {path.relative_to(root)}")

    setup_skill = root / ".agents/plugins/unity-agent/skills/unity-agent-setup/SKILL.md"
    if setup_skill.is_file():
        text = setup_skill.read_text(encoding="utf-8").casefold()
        for token in FORBIDDEN_ENTRY_TEXT:
            if token in text:
                errors.append(f"Entry setup skill must not directly invoke Provider: {token}")
        if "unity-agent setup" not in text:
            errors.append("Entry setup skill must route through unity-agent setup")
    else:
        errors.append("UnityAgent setup skill is missing")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("UnityAgent five-layer validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("UnityAgent five-layer validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
