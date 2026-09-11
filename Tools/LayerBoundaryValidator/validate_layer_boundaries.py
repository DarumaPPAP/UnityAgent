#!/usr/bin/env python3
"""Validate the product-facing UnityAgent five-layer dependency contract."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

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
CANONICAL_VERSION = "0.0.6-beta"
_GUID_PATTERN = re.compile(r"^guid:\s*([0-9a-f]{32})$", re.MULTILINE)


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping: {path}")
    return value


def _validate_upm_meta_files(package_root: Path, root: Path) -> list[str]:
    """Ensure every imported package asset/folder ships with a stable Unity .meta file."""
    errors: list[str] = []
    guid_owners: dict[str, Path] = {}
    for path in sorted(package_root.rglob("*")):
        relative = path.relative_to(package_root)
        if path.name.endswith(".meta") or any(part.endswith("~") for part in relative.parts):
            continue
        meta_path = path.with_name(path.name + ".meta")
        if not meta_path.is_file():
            errors.append(f"UnityAgent UPM asset is missing .meta: {path.relative_to(root)}")
            continue
        try:
            meta_text = meta_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"UnityAgent UPM meta is unreadable: {meta_path.relative_to(root)}: {exc}")
            continue
        match = _GUID_PATTERN.search(meta_text)
        if match is None:
            errors.append(f"UnityAgent UPM meta has no canonical 32-hex guid: {meta_path.relative_to(root)}")
            continue
        guid = match.group(1)
        owner = guid_owners.get(guid)
        if owner is not None:
            errors.append(
                "UnityAgent UPM meta GUID is duplicated: "
                f"{owner.relative_to(root)} and {meta_path.relative_to(root)}"
            )
        else:
            guid_owners[guid] = meta_path
        if path.is_dir() and "folderAsset: yes" not in meta_text:
            errors.append(f"UnityAgent UPM folder meta must declare folderAsset: yes: {meta_path.relative_to(root)}")
    return errors


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

    for relative in (
        "Runtime/Contracts/entry-request.schema.yaml",
        "Runtime/Contracts/toolchain-setup-request.schema.yaml",
        "Runtime/Contracts/install-receipt.schema.yaml",
        "Packages/com.darumappap.unity-agent/package.json",
    ):
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
        errors.extend(_validate_upm_meta_files(package_path.parent, root))
        for path in sorted(package_path.parent.glob("Editor/*.cs")):
            text = path.read_text(encoding="utf-8").casefold()
            if "unity-artist" in text or "unity artist" in text:
                errors.append(f"Unity UI Entry must not invoke UnityArtistCLI directly: {path.relative_to(root)}")
            if "filename = \"unity\"" in text:
                errors.append(f"Unity UI Entry must not invoke Official Unity CLI directly: {path.relative_to(root)}")
            if "filename = \"codex\"" in text or "codex plugin marketplace" in text or "codex plugin add" in text:
                errors.append(f"Unity UI Entry must not invoke Codex Plugin commands directly: {path.relative_to(root)}")

        codex_resolver_path = package_path.parent / "Editor/UnityAgentCodexPathResolver.cs"
        control_plane_resolver_path = package_path.parent / "Editor/UnityAgentControlPlanePathResolver.cs"
        bootstrap_path = package_path.parent / "Editor/UnityAgentControlPlaneBootstrap.cs"
        bootstrap_script_path = package_path.parent / "Editor/Bootstrap~/install-control-plane.ps1"
        setup_window_path = package_path.parent / "Editor/UnityAgentSetupWindow.cs"
        control_plane_client_path = package_path.parent / "Editor/UnityAgentControlPlaneClient.cs"

        if not codex_resolver_path.is_file():
            errors.append("UnityAgent Codex path resolver is missing")
        else:
            resolver_text = codex_resolver_path.read_text(encoding="utf-8").casefold()
            for forbidden in ("system.diagnostics", "processstartinfo", "process.start", "--version"):
                if forbidden in resolver_text:
                    errors.append(
                        "Unity Entry Codex path resolver must remain discovery-only and must not execute Codex: "
                        + forbidden
                    )

        if not control_plane_resolver_path.is_file():
            errors.append("UnityAgent Control Plane path resolver is missing")
        else:
            resolver_text = control_plane_resolver_path.read_text(encoding="utf-8").casefold()
            for forbidden in ("system.diagnostics", "processstartinfo", "process.start"):
                if forbidden in resolver_text:
                    errors.append(
                        "Unity Entry Control Plane path resolver must remain discovery-only: " + forbidden
                    )
            if "unity_agent_control_plane" not in resolver_text:
                errors.append("Control Plane path resolver must read the stable UNITY_AGENT_CONTROL_PLANE hint")
            if "environmentvariabletarget.user" not in resolver_text:
                errors.append("Control Plane path resolver must inspect the persisted User environment")

        if not bootstrap_path.is_file():
            errors.append("UnityAgent Control Plane bootstrap runner is missing")
        else:
            bootstrap_text = bootstrap_path.read_text(encoding="utf-8")
            bootstrap_folded = bootstrap_text.casefold()
            if f'internal const string Channel = "{CANONICAL_VERSION}"' not in bootstrap_text:
                errors.append("Control Plane bootstrap channel must match the canonical version")
            if f'internal const string ReleaseTag = "v{CANONICAL_VERSION}"' not in bootstrap_text:
                errors.append("Control Plane bootstrap release tag must match the canonical version")
            if "PackageInfo.FindForAssembly" not in bootstrap_text or "Bootstrap~" not in bootstrap_text:
                errors.append("Control Plane bootstrap must execute the package-local pinned bootstrap script")
            for forbidden in ("codex plugin", "unity-artist", "unity artist"):
                if forbidden in bootstrap_folded:
                    errors.append("Control Plane bootstrap must not mutate Providers or Codex directly: " + forbidden)

        if not bootstrap_script_path.is_file():
            errors.append("UnityAgent package-local Control Plane bootstrap script is missing")
        else:
            script_text = bootstrap_script_path.read_text(encoding="utf-8")
            script_folded = script_text.casefold()
            for required in ("SHA256SUMS.txt", "Get-FileHash", '"--user"', "UNITY_AGENT_CONTROL_PLANE"):
                if required not in script_text:
                    errors.append("Control Plane bootstrap script is missing trust/install guard: " + required)
            for forbidden in ("codex plugin", "unity-artist", "main/scripts/install.ps1"):
                if forbidden in script_folded:
                    errors.append("Control Plane bootstrap script exceeds its bootstrap-only scope: " + forbidden)

        if setup_window_path.is_file():
            setup_text = setup_window_path.read_text(encoding="utf-8")
            if "UnityAgentCodexPathResolver.Resolve" not in setup_text:
                errors.append("UnityAgent Setup Window must use the canonical Codex path resolver")
            if "UnityAgentControlPlanePathResolver.Resolve" not in setup_text:
                errors.append("UnityAgent Setup Window must use the canonical Control Plane path resolver")
            if "UnityAgentControlPlaneBootstrap.Start" not in setup_text:
                errors.append("UnityAgent Setup Window must expose the bounded Control Plane bootstrap path")
            if "Install Control Plane" not in setup_text:
                errors.append("UnityAgent Setup Window must present an explicit Control Plane bootstrap action")
            if 'hostCommand = "unity-agent"' in setup_text:
                errors.append("UnityAgent Setup Window must not fall back to a bare unity-agent command")

        if control_plane_client_path.is_file():
            client_text = control_plane_client_path.read_text(encoding="utf-8")
            if "--codex-path" not in client_text:
                errors.append("UnityAgent Control Plane client must pass the resolved Codex path through --codex-path")

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
