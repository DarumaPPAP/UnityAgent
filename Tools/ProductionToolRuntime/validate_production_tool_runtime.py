#!/usr/bin/env python3
"""Fail-closed validator for the Production Tool Runtime cutover contract."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PROFILES = {
    "FULL",
    "CLI_ONLY",
    "MCP_ONLY",
    "NATIVE_EDITOR",
    "FILES_ONLY",
    "SAFE_MODE",
    "NO_EDITOR",
    "PLAYER_UNAVAILABLE",
}
FORBIDDEN_PROVIDER_TOKENS = {"unity_cli", "myunitymcp", "coplay_mcp", "player_runtime"}


def _yaml(relative: str) -> dict[str, Any]:
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML mapping: {relative}")
    return value


def validate(root: Path = ROOT) -> list[str]:
    global ROOT
    original = ROOT
    ROOT = root.resolve()
    errors: list[str] = []
    try:
        legacy = ROOT / "Context/Selection/mcp-selection.yaml"
        if legacy.exists():
            errors.append("legacy Context/Selection/mcp-selection.yaml must be removed after cutover")

        context_catalog = _yaml("Context/Selection/context-catalog.yaml")
        if context_catalog.get("capability_catalog") != "Context/Selection/tool-capability-catalog.yaml":
            errors.append("Context catalog must bind the canonical capability catalog")
        if "mcp_selection" in context_catalog:
            errors.append("Context catalog must not retain mcp_selection authority")
        for route_id, route in (context_catalog.get("routes") or {}).items():
            if isinstance(route, dict) and "mcp_selection" in route:
                errors.append(f"{route_id}: legacy mcp_selection route contract remains")

        capability_context = _yaml("Context/Selection/tool-capability-catalog.yaml")
        capability_policy = _yaml("Policy/Security/tool-capability-policy.yaml")
        provider_registry = _yaml("Runtime/Tooling/provider_registry.yaml")
        context_caps = set((capability_context.get("capabilities") or {}).keys())
        policy_caps = set((capability_policy.get("capabilities") or {}).keys())
        runtime_caps = set((provider_registry.get("capability_requirements") or {}).keys())
        if context_caps != policy_caps or context_caps != runtime_caps:
            errors.append("Policy/Context/Runtime capability vocabularies are not identical")
        if not (capability_context.get("rules") or {}).get("context_does_not_select_provider"):
            errors.append("Context capability catalog must deny Provider selection authority")
        if not (capability_policy.get("rules") or {}).get("policy_does_not_select_provider"):
            errors.append("Policy capability contract must deny Provider selection authority")

        orchestrator = (ROOT / "Orchestration/Orchestrator/orchestrator.py").read_text(encoding="utf-8")
        if '"capability_contract_mode": "authoritative"' not in orchestrator:
            errors.append("Orchestration Runtime handoff is not authoritative")
        if '"capability_contract_mode": "shadow"' in orchestrator:
            errors.append("shadow capability handoff remains after Production cutover")
        provider_guard_markers = {
            '"provider_ref" in request',
            '"provider" in request',
            "provider-independent CapabilityRequest",
        }
        if not provider_guard_markers.issubset(set(marker for marker in provider_guard_markers if marker in orchestrator)):
            errors.append("Orchestrator must reject Provider identity in Runtime handoff")

        broker = (ROOT / "Runtime/Tooling/tool_broker.py").read_text(encoding="utf-8")
        dispatcher = ROOT / "Runtime/Dispatcher/tool_runtime_dispatcher.py"
        if "def dispatch(" not in broker or not dispatcher.is_file():
            errors.append("Tool Broker is not connected to the Production dispatcher")
        if "dispatch_capability" not in dispatcher.read_text(encoding="utf-8"):
            errors.append("Production dispatcher entrypoint is missing")

        routing = _yaml("Orchestration/ToolRouting/capability-routing.yaml")
        semantic_text = yaml.safe_dump(routing, sort_keys=True).casefold()
        for token in FORBIDDEN_PROVIDER_TOKENS:
            if token in semantic_text:
                errors.append(f"Orchestration semantic routing leaked Provider token: {token}")

        matrix = _yaml("Eval/Datasets/Behavior/production-tool-runtime-environment-matrix.yaml")
        if matrix.get("routing_authority") is not False:
            errors.append("Environment Matrix must remain descriptive/Eval-only")
        profiles = set((matrix.get("profiles") or {}).keys())
        if profiles != EXPECTED_PROFILES:
            errors.append(f"Environment Matrix profiles mismatch: {sorted(profiles)}")
        rules = matrix.get("rules") or {}
        if rules.get("baseline_auto_update") != "prohibited":
            errors.append("Environment Matrix must prohibit Baseline auto-update")
        if rules.get("no_silent_safety_or_evidence_downgrade") is not True:
            errors.append("Environment Matrix must prohibit silent safety/evidence downgrade")

        active_roots = ["Policy", "Context", "Orchestration", "Runtime"]
        for relative_root in active_roots:
            for path in (ROOT / relative_root).rglob("*"):
                if not path.is_file() or path.suffix.lower() not in {".yaml", ".yml", ".py", ".md"}:
                    continue
                text = path.read_text(encoding="utf-8")
                if "Catalog/mcp-catalog.yaml" in text or "Catalog/creator-catalog.yaml" in text or "Catalog/capability-catalog.yaml" in text:
                    errors.append(f"legacy root Catalog reference remains in active authority: {path.relative_to(ROOT)}")

        materializer = (ROOT / "Context/Assembly/materialize_context.py").read_text(encoding="utf-8")
        required_revisions = {
            '"architecture_version": "v4.0"',
            '"runtime_profile_revision": "runtime-profiles-v1"',
            '"tool_schema_revision": "production-tool-runtime-v1"',
            '"evidence_schema_revision": "1.2"',
            '"eval_contract_revision": "1.2"',
        }
        for marker in required_revisions:
            if marker not in materializer:
                errors.append(f"Production DefinitionFingerprint marker missing: {marker}")
    finally:
        ROOT = original
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Production Tool Runtime validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Production Tool Runtime validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
